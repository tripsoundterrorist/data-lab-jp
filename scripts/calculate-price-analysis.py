from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import fmean
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = ROOT / "data" / "data-lab.db"
ANALYSIS_NAME = "price_analysis"
VERSION = "0.1"
PERCENTILE_METHOD = "midrank_percent_rank"
GENRE_MINIMUM_SAMPLE = 20
MAKER_MINIMUM_SAMPLE = 10
JST_OFFSET = timedelta(hours=9)

# Price Analysis is descriptive. It is neither a market-price estimate nor a
# value score, and a lower or higher observed-set position is not "better".
CAVEATS = [
    "DATE_SORT_LEADING_500_ITEMS",
    "OBSERVED_SET_IS_PART_OF_API_TOTAL_50000",
    "SOURCE_DATE_MEANING_UNCONFIRMED",
    "REVIEW_DATA_UNAVAILABLE",
    "RANK_DATA_UNAVAILABLE",
    "SHORT_OBSERVATION_WINDOW",
    "GENRE_MULTI_MEMBERSHIP",
    "MAKER_SMALL_SAMPLES",
    "CURRENT_PRICE_IS_AS_OBSERVED",
]


class PriceAnalysisError(Exception):
    pass


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print("price analysis failed: INVALID_ARGUMENT", file=sys.stderr)
        raise SystemExit(2)


def parse_timestamp(value: str, argument_name: str = "timestamp") -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{argument_name} must be an ISO8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{argument_name} must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def parse_as_of(value: str) -> datetime:
    try:
        return parse_timestamp(value, "--as-of")
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def positive_item_id(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("item ID must be a positive integer") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("item ID must be a positive integer")
    return parsed


def read_only_connection(path: Path) -> sqlite3.Connection:
    resolved = path.resolve()
    if not resolved.is_file():
        raise PriceAnalysisError("DATABASE_NOT_FOUND")
    connection = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def distribution(values: list[float], include_p10_p95: bool = False) -> dict[str, Any]:
    if not values:
        result: dict[str, Any] = {
            "count": 0,
            "min": None,
            "p25": None,
            "median": None,
            "mean": None,
            "p75": None,
            "p90": None,
            "max": None,
        }
        if include_p10_p95:
            result.update({"p10": None, "p95": None})
        return result
    result = {
        "count": len(values),
        "min": min(values),
        "p25": percentile(values, 0.25),
        "median": percentile(values, 0.50),
        "mean": fmean(values),
        "p75": percentile(values, 0.75),
        "p90": percentile(values, 0.90),
        "max": max(values),
    }
    if include_p10_p95:
        result.update(
            {"p10": percentile(values, 0.10), "p95": percentile(values, 0.95)}
        )
    return result


def rounded_distribution(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: round(value, 2) if isinstance(value, float) else value
        for key, value in result.items()
    }


def midrank_percentile(value: float, population: list[float]) -> float | None:
    """Return a tie-aware position from 0 to 100 within this observed set.

    Ties receive the midpoint of the ranks they occupy. With more than one
    observation, the minimum unique value is 0 and the maximum unique value is
    100. A one-item population is defined as 50.
    """
    if not population:
        return None
    less = sum(candidate < value for candidate in population)
    equal = sum(candidate == value for candidate in population)
    if equal == 0:
        return None
    if len(population) == 1:
        return 50.0
    midrank_zero_based = less + (equal - 1) / 2.0
    return 100.0 * midrank_zero_based / (len(population) - 1)


def price_band(position: float | None) -> dict[str, str] | None:
    if position is None:
        return None
    if position < 20.0:
        return {"code": "lower_range", "en": "Lower range", "ja": "低位帯"}
    if position < 40.0:
        return {
            "code": "lower_middle_range",
            "en": "Lower-middle range",
            "ja": "中低位帯",
        }
    if position < 60.0:
        return {"code": "middle_range", "en": "Middle range", "ja": "中央帯"}
    if position < 80.0:
        return {
            "code": "upper_middle_range",
            "en": "Upper-middle range",
            "ja": "中高位帯",
        }
    return {"code": "upper_range", "en": "Upper range", "ja": "高位帯"}


def parse_entity_ids(value: Any) -> tuple[list[str], bool]:
    if value is None:
        return [], False
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return [], True
    if not isinstance(parsed, list):
        return [], True
    identifiers: list[str] = []
    for entity in parsed:
        if not isinstance(entity, dict) or entity.get("id") is None:
            continue
        identifier = str(entity["id"])
        if identifier not in identifiers:
            identifiers.append(identifier)
    return identifiers, False


def jst_date(value: datetime) -> str:
    return (value + JST_OFFSET).date().isoformat()


def nonnegative_span_days(first: datetime, last: datetime) -> float:
    return max((last - first).total_seconds() / 86400.0, 0.0)


ITEM_SQL = """
SELECT id AS item_id, genre_json, maker_json
FROM items
ORDER BY id
"""


SNAPSHOT_SQL = """
SELECT id, item_id, observed_at, price_min
FROM item_snapshots
ORDER BY item_id, observed_at, id
"""


def read_source_data(
    connection: sqlite3.Connection, as_of: datetime
) -> tuple[dict[int, dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    items: dict[int, dict[str, Any]] = {}
    for row in connection.execute(ITEM_SQL):
        genre_ids, invalid_genre = parse_entity_ids(row["genre_json"])
        maker_ids, invalid_maker = parse_entity_ids(row["maker_json"])
        warnings = []
        if invalid_genre:
            warnings.append("INVALID_GENRE_JSON")
        if invalid_maker:
            warnings.append("INVALID_MAKER_JSON")
        items[row["item_id"]] = {
            "genre_ids": genre_ids,
            "maker_ids": maker_ids,
            "warnings": warnings,
            "future_observation_count": 0,
            "invalid_observation_timestamp_count": 0,
        }

    snapshots: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in connection.execute(SNAPSHOT_SQL):
        item = items.get(row["item_id"])
        if item is None:
            continue
        try:
            observed_at = parse_timestamp(row["observed_at"])
        except ValueError:
            item["invalid_observation_timestamp_count"] += 1
            continue
        if observed_at > as_of:
            item["future_observation_count"] += 1
            continue
        snapshots[row["item_id"]].append(
            {
                "id": row["id"],
                "observed_at": observed_at,
                "price_min": row["price_min"],
            }
        )
    return items, snapshots


def build_item_history(
    item_id: int,
    metadata: dict[str, Any],
    snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    warnings = list(metadata["warnings"])
    if metadata["future_observation_count"]:
        warnings.append("FUTURE_OBSERVATIONS_EXCLUDED")
    if metadata["invalid_observation_timestamp_count"]:
        warnings.append("INVALID_OBSERVATION_TIMESTAMPS_EXCLUDED")

    ordered = sorted(snapshots, key=lambda row: (row["observed_at"], row["id"]))
    latest_snapshot = ordered[-1] if ordered else None
    price_rows = [row for row in ordered if row["price_min"] is not None]
    current_available = bool(
        latest_snapshot is not None and latest_snapshot["price_min"] is not None
    )
    current_price = latest_snapshot["price_min"] if current_available else None
    if not current_available:
        warnings.append("CURRENT_PRICE_UNAVAILABLE")

    if price_rows:
        first = price_rows[0]
        latest_price = price_rows[-1]
        prices = [row["price_min"] for row in price_rows]
        distinct_dates = len({jst_date(row["observed_at"]) for row in price_rows})
        span_days = nonnegative_span_days(first["observed_at"], latest_price["observed_at"])
        history = {
            "first_observed_price": first["price_min"],
            "first_price_observed_at": iso_utc(first["observed_at"]),
            "latest_observed_price": latest_price["price_min"],
            "latest_price_observed_at": iso_utc(latest_price["observed_at"]),
            "min_observed_price": min(prices),
            "max_observed_price": max(prices),
            "price_observation_count": len(price_rows),
            "distinct_price_observation_dates": distinct_dates,
            "price_observation_span_days": span_days,
        }
    else:
        distinct_dates = 0
        span_days = 0.0
        history = {
            "first_observed_price": None,
            "first_price_observed_at": None,
            "latest_observed_price": None,
            "latest_price_observed_at": None,
            "min_observed_price": None,
            "max_observed_price": None,
            "price_observation_count": 0,
            "distinct_price_observation_dates": 0,
            "price_observation_span_days": 0.0,
        }

    return {
        "item_id": item_id,
        "genre_ids": metadata["genre_ids"],
        "maker_ids": metadata["maker_ids"],
        "current_price": current_price,
        "current_price_observed_at": (
            iso_utc(latest_snapshot["observed_at"])
            if current_available and latest_snapshot
            else None
        ),
        "price_available": current_available,
        "price_history_stats": history,
        "warnings": sorted(set(warnings)),
    }


def group_populations(
    items: list[dict[str, Any]], entity_key: str
) -> dict[str, list[float]]:
    populations: dict[str, list[float]] = defaultdict(list)
    for item in items:
        if not item["price_available"]:
            continue
        for entity_id in item[entity_key]:
            populations[entity_id].append(item["current_price"])
    return populations


def comparison(
    entity_id: str,
    current_price: float | None,
    populations: dict[str, list[float]],
    minimum_sample: int,
) -> dict[str, Any]:
    population = populations.get(entity_id, [])
    base = {
        "id": entity_id,
        "sample_size": len(population),
        "minimum_sample_size": minimum_sample,
    }
    if current_price is None:
        return {**base, "status": "price_unavailable", "median": None, "percentile": None}
    if len(population) < minimum_sample:
        return {**base, "status": "insufficient_sample", "median": None, "percentile": None}
    position = midrank_percentile(current_price, population)
    return {
        **base,
        "status": "available",
        "median": percentile(population, 0.50),
        "percentile": round(position, 2) if position is not None else None,
        "percentile_method": PERCENTILE_METHOD,
    }


def group_analysis(
    populations: dict[str, list[float]],
    thresholds: tuple[int, ...],
    items: list[dict[str, Any]],
    entity_key: str,
    recommended_minimum: int,
) -> dict[str, Any]:
    sizes = [len(population) for population in populations.values()]
    available_items_by_threshold = {
        str(threshold): sum(
            item["price_available"]
            and any(
                len(populations.get(entity_id, [])) >= threshold
                for entity_id in item[entity_key]
            )
            for item in items
        )
        for threshold in thresholds
    }
    return {
        "distinct_groups": len(populations),
        "sample_size_distribution": rounded_distribution(distribution(sizes)),
        "groups_by_minimum_sample": {
            str(threshold): sum(size >= threshold for size in sizes)
            for threshold in thresholds
        },
        "comparable_items_by_minimum_sample": available_items_by_threshold,
        "recommended_minimum_sample": recommended_minimum,
        "comparable_items_at_recommended_minimum": available_items_by_threshold[
            str(recommended_minimum)
        ],
    }


def build_observed_set(items: list[dict[str, Any]]) -> tuple[dict[str, Any], list[float]]:
    prices = [item["current_price"] for item in items if item["price_available"]]
    counts = Counter(prices)
    largest_tie = max(counts.values(), default=0)
    result = rounded_distribution(distribution(prices, include_p10_p95=True))
    result.update(
        {
            "evaluated_items": len(items),
            "price_available_items": len(prices),
            "price_coverage": round(len(prices) / len(items), 6) if items else None,
            "distinct_price_count": len(counts),
            "largest_tie_count": largest_tie,
            "largest_tie_share": round(largest_tie / len(prices), 6) if prices else None,
            "scope": "current_data_lab_observed_set",
            "percentile_method": PERCENTILE_METHOD,
        }
    )
    return result, prices


def public_item(
    item: dict[str, Any],
    observed_prices: list[float],
    genre_populations: dict[str, list[float]],
    maker_populations: dict[str, list[float]],
) -> dict[str, Any]:
    position = (
        midrank_percentile(item["current_price"], observed_prices)
        if item["price_available"]
        else None
    )
    genre_comparisons = [
        comparison(
            genre_id,
            item["current_price"],
            genre_populations,
            GENRE_MINIMUM_SAMPLE,
        )
        for genre_id in item["genre_ids"]
    ]
    maker_comparisons = [
        comparison(
            maker_id,
            item["current_price"],
            maker_populations,
            MAKER_MINIMUM_SAMPLE,
        )
        for maker_id in item["maker_ids"]
    ]
    return {
        "item_id": item["item_id"],
        "current_price": item["current_price"],
        "current_price_observed_at": item["current_price_observed_at"],
        "price_available": item["price_available"],
        "percentile": round(position, 2) if position is not None else None,
        "percentile_method": PERCENTILE_METHOD,
        "price_band": price_band(position),
        "price_history_stats": item["price_history_stats"],
        "genre_comparisons": genre_comparisons,
        "genre_comparison_available": any(
            entry["status"] == "available" for entry in genre_comparisons
        ),
        "maker_comparison": {
            "comparisons": maker_comparisons,
            "available": any(
                entry["status"] == "available" for entry in maker_comparisons
            ),
        },
        "warnings": item["warnings"],
    }


def calculate(
    database_path: Path, as_of: datetime, item_id: int | None = None
) -> dict[str, Any]:
    with closing(read_only_connection(database_path)) as connection:
        metadata, snapshots = read_source_data(connection, as_of)
    if item_id is not None and item_id not in metadata:
        raise PriceAnalysisError("ITEM_NOT_FOUND")

    histories = [
        build_item_history(identifier, item, snapshots.get(identifier, []))
        for identifier, item in metadata.items()
    ]
    observed_set, observed_prices = build_observed_set(histories)
    genre_populations = group_populations(histories, "genre_ids")
    maker_populations = group_populations(histories, "maker_ids")
    genre_analysis = group_analysis(
        genre_populations,
        (10, 20, 30),
        histories,
        "genre_ids",
        GENRE_MINIMUM_SAMPLE,
    )
    maker_analysis = group_analysis(
        maker_populations,
        (5, 10, 20),
        histories,
        "maker_ids",
        MAKER_MINIMUM_SAMPLE,
    )
    selected = histories if item_id is None else [next(x for x in histories if x["item_id"] == item_id)]
    public_items = [
        public_item(item, observed_prices, genre_populations, maker_populations)
        for item in selected
    ]
    return {
        "analysis_name": ANALYSIS_NAME,
        "version": VERSION,
        "as_of": iso_utc(as_of),
        "observed_set": observed_set,
        "genre_analysis": genre_analysis,
        "maker_analysis": maker_analysis,
        "items": public_items,
        "caveats": CAVEATS,
    }


def print_observed_set(result: dict[str, Any]) -> None:
    observed = result["observed_set"]
    print("PRICE ANALYSIS v0.1")
    print(f"As of: {result['as_of']}")
    print("Observed set:")
    print(f"  evaluated items: {observed['evaluated_items']}")
    print(f"  price available items: {observed['price_available_items']}")
    print(f"  price coverage: {observed['price_coverage']}")
    for key in ("min", "p10", "p25", "median", "mean", "p75", "p90", "p95", "max"):
        print(f"  {key}: {observed[key]}")
    print(f"  distinct prices: {observed['distinct_price_count']}")
    print(f"  largest tie: {observed['largest_tie_count']}")
    print("Comparability:")
    print(
        "  genre items: "
        f"{result['genre_analysis']['comparable_items_at_recommended_minimum']}"
    )
    print(
        "  maker items: "
        f"{result['maker_analysis']['comparable_items_at_recommended_minimum']}"
    )


def print_item(result: dict[str, Any]) -> None:
    item = result["items"][0]
    print_observed_set(result)
    print("Item:")
    print(f"  item_id: {item['item_id']}")
    print(f"  current price: {item['current_price']}")
    print(f"  current price observed at: {item['current_price_observed_at']}")
    print(f"  observed-set percentile: {item['percentile']}")
    band = item["price_band"]
    print(f"  price band: {band['en'] if band else 'unavailable'}")
    print(
        "  genre comparison: "
        f"{'available' if item['genre_comparison_available'] else 'insufficient'}"
    )
    print(
        "  maker comparison: "
        f"{'available' if item['maker_comparison']['available'] else 'insufficient'}"
    )
    print("  warnings:")
    if item["warnings"]:
        for warning in item["warnings"]:
            print(f"    {warning}")
    else:
        print("    none")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = SafeArgumentParser(
        description="Read-only observed-set Price Analysis v0.1."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--item-id", type=positive_item_id)
    parser.add_argument("--as-of", type=parse_as_of)
    return parser.parse_args(argv)


def error_result(code: str) -> dict[str, str]:
    return {"analysis_name": ANALYSIS_NAME, "version": VERSION, "error": code}


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    as_of = args.as_of or datetime.now(timezone.utc)
    try:
        result = calculate(args.db, as_of, args.item_id)
    except PriceAnalysisError as error:
        if args.json:
            print(json.dumps(error_result(str(error)), ensure_ascii=False))
        else:
            print(f"price analysis failed: {error}", file=sys.stderr)
        return 2
    except (OSError, sqlite3.Error):
        if args.json:
            print(json.dumps(error_result("DATABASE_ACCESS_ERROR"), ensure_ascii=False))
        else:
            print("price analysis failed: DATABASE_ACCESS_ERROR", file=sys.stderr)
        return 2
    except Exception:
        if args.json:
            print(json.dumps(error_result("UNEXPECTED_ERROR"), ensure_ascii=False))
        else:
            print("price analysis failed: UNEXPECTED_ERROR", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    elif args.item_id is not None:
        print_item(result)
    else:
        print_observed_set(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
