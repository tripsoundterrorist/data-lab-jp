from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = ROOT / "data" / "data-lab.db"
SCORE_NAME = "data_confidence"
SCORE_VERSION = "0.1"

# This is a data-confidence calculation, not DATA LAB's future DATA SCORE.
# Review, rank, popularity, price direction, and trend are intentionally absent.
WEIGHTS = {
    "freshness": 0.20,
    "observation_depth": 0.25,
    "metadata_completeness": 0.20,
    "price_data": 0.20,
    "temporal_confidence": 0.15,
}


class ConfidenceCalculationError(Exception):
    pass


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print("data confidence calculation failed: INVALID_ARGUMENT", file=sys.stderr)
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


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_as_of(value: str) -> datetime:
    try:
        return parse_timestamp(value, "--as-of")
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def positive_item_id(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("item ID must be a positive integer") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("item ID must be a positive integer")
    return parsed


def sat(value: float, cap: float) -> float:
    if cap <= 0:
        raise ValueError("SAT cap must be positive")
    return 100.0 * min(math.log1p(max(value, 0.0)) / math.log1p(cap), 1.0)


def freshness_score(age_days: float) -> float:
    return 100.0 * 2.0 ** (-max(age_days, 0.0) / 14.0)


def observation_depth_score(distinct_runs: int, distinct_dates: int) -> float:
    return 0.20 * sat(distinct_runs, 8) + 0.80 * sat(distinct_dates, 8)


def valid_nonempty_json_array(value: Any) -> tuple[bool, bool]:
    if value is None:
        return False, False
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return False, True
    return isinstance(parsed, list) and bool(parsed), False


def metadata_score(row: sqlite3.Row) -> tuple[float, list[str]]:
    warnings: list[str] = []
    maker_ok, maker_invalid = valid_nonempty_json_array(row["maker_json"])
    genre_ok, genre_invalid = valid_nonempty_json_array(row["genre_json"])
    if maker_invalid:
        warnings.append("INVALID_MAKER_JSON")
    if genre_invalid:
        warnings.append("INVALID_GENRE_JSON")
    score = (
        20.0 * maker_ok
        + 20.0 * genre_ok
        + 15.0 * bool(row["image_url_large"])
        + 25.0 * bool(row["item_url"])
        + 20.0 * bool(row["product_id"])
    )
    return score, warnings


def price_data_score(
    current_available: bool,
    distinct_price_dates: int,
    price_span_days: float,
) -> float:
    if not current_available:
        return 0.0
    repeat = sat(max(distinct_price_dates - 1, 0), 7)
    span = sat(price_span_days, 30)
    return 60.0 + 0.25 * repeat + 0.15 * span


def temporal_confidence_score(span_days: float, distinct_dates: int) -> float:
    span = sat(span_days, 30)
    active_dates = 100.0 * min(max(distinct_dates - 1, 0) / 6.0, 1.0)
    return 0.70 * span + 0.30 * active_dates


def label_for_score(score: float) -> dict[str, str]:
    if score >= 95.0:
        return {"code": "very_high", "en": "Very High", "ja": "非常に高い"}
    if score >= 85.0:
        return {"code": "high", "en": "High", "ja": "高い"}
    if score >= 70.0:
        return {"code": "medium", "en": "Medium", "ja": "中程度"}
    if score >= 50.0:
        return {"code": "limited", "en": "Limited", "ja": "限定的"}
    if score >= 25.0:
        return {"code": "low", "en": "Low", "ja": "低い"}
    return {"code": "very_low", "en": "Very Low", "ja": "非常に低い"}


def read_only_connection(path: Path) -> sqlite3.Connection:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ConfidenceCalculationError("DATABASE_NOT_FOUND")
    connection = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


AGGREGATE_SQL = """
WITH latest_snapshot AS (
  SELECT item_id, price_min
  FROM (
    SELECT item_id, price_min,
           ROW_NUMBER() OVER (
             PARTITION BY item_id
             ORDER BY observed_at DESC, id DESC
           ) AS row_number
    FROM item_snapshots
  )
  WHERE row_number = 1
), observation_stats AS (
  SELECT
    item_id,
    COUNT(*) AS snapshot_count,
    COUNT(DISTINCT collection_run_id) AS distinct_run_count,
    COUNT(DISTINCT date(observed_at, '+9 hours')) AS distinct_observation_dates,
    MIN(observed_at) AS first_observed_at,
    MAX(observed_at) AS last_observed_at,
    COUNT(DISTINCT CASE
      WHEN price_min IS NOT NULL THEN date(observed_at, '+9 hours')
    END) AS distinct_price_observation_dates,
    MIN(CASE WHEN price_min IS NOT NULL THEN observed_at END)
      AS first_price_observed_at,
    MAX(CASE WHEN price_min IS NOT NULL THEN observed_at END)
      AS last_price_observed_at
  FROM item_snapshots
  GROUP BY item_id
)
SELECT
  i.id AS item_id,
  i.maker_json,
  i.genre_json,
  i.image_url_large,
  i.item_url,
  i.product_id,
  COALESCE(o.snapshot_count, 0) AS snapshot_count,
  COALESCE(o.distinct_run_count, 0) AS distinct_run_count,
  COALESCE(o.distinct_observation_dates, 0) AS distinct_observation_dates,
  o.first_observed_at,
  o.last_observed_at,
  COALESCE(o.distinct_price_observation_dates, 0)
    AS distinct_price_observation_dates,
  o.first_price_observed_at,
  o.last_price_observed_at,
  l.price_min AS current_price_min
FROM items AS i
LEFT JOIN observation_stats AS o ON o.item_id = i.id
LEFT JOIN latest_snapshot AS l ON l.item_id = i.id
WHERE (? IS NULL OR i.id = ?)
ORDER BY i.id
"""


def optional_db_timestamp(
    value: Any, warning_code: str, warnings: list[str]
) -> datetime | None:
    if value is None:
        return None
    try:
        return parse_timestamp(value)
    except ValueError:
        warnings.append(warning_code)
        return None


def nonnegative_span_days(first: datetime | None, last: datetime | None) -> float:
    if first is None or last is None:
        return 0.0
    return max((last - first).total_seconds() / 86400.0, 0.0)


def calculate_item(row: sqlite3.Row, as_of: datetime, calculated_at: str) -> dict[str, Any]:
    warnings: list[str] = []
    first = optional_db_timestamp(
        row["first_observed_at"], "INVALID_FIRST_OBSERVED_AT", warnings
    )
    last = optional_db_timestamp(
        row["last_observed_at"], "INVALID_LAST_OBSERVED_AT", warnings
    )
    price_first = optional_db_timestamp(
        row["first_price_observed_at"], "INVALID_FIRST_PRICE_OBSERVED_AT", warnings
    )
    price_last = optional_db_timestamp(
        row["last_price_observed_at"], "INVALID_LAST_PRICE_OBSERVED_AT", warnings
    )

    if row["snapshot_count"] == 0:
        warnings.append("NO_OBSERVATIONS")
    if last is not None and last > as_of:
        warnings.append("FUTURE_OBSERVED_AT")

    age_days = (
        max((as_of - last).total_seconds() / 86400.0, 0.0)
        if last is not None
        else math.inf
    )
    observation_span_days = nonnegative_span_days(first, last)
    price_span_days = nonnegative_span_days(price_first, price_last)
    metadata, metadata_warnings = metadata_score(row)
    warnings.extend(metadata_warnings)

    freshness = 0.0 if not math.isfinite(age_days) else freshness_score(age_days)
    depth = observation_depth_score(
        row["distinct_run_count"], row["distinct_observation_dates"]
    )
    price = price_data_score(
        row["current_price_min"] is not None,
        row["distinct_price_observation_dates"],
        price_span_days,
    )
    temporal = temporal_confidence_score(
        observation_span_days, row["distinct_observation_dates"]
    )
    components = {
        "freshness": freshness,
        "observation_depth": depth,
        "metadata_completeness": metadata,
        "price_data": price,
        "temporal_confidence": temporal,
    }
    unbounded_score = sum(components[key] * WEIGHTS[key] for key in WEIGHTS)
    score = min(max(unbounded_score, 0.0), 100.0)

    return {
        "item_id": row["item_id"],
        "score_name": SCORE_NAME,
        "score_version": SCORE_VERSION,
        "calculated_at": calculated_at,
        "as_of": iso_utc(as_of),
        "score": round(score, 1),
        "score_raw": score,
        "label": label_for_score(score),
        "components": {key: round(value, 1) for key, value in components.items()},
        "components_raw": components,
        "observation_stats": {
            "snapshot_count": row["snapshot_count"],
            "distinct_collection_run_count": row["distinct_run_count"],
            "distinct_observation_date_count": row["distinct_observation_dates"],
            "first_observed_at": row["first_observed_at"],
            "last_observed_at": row["last_observed_at"],
            "observation_span_days": observation_span_days,
            "distinct_price_observation_date_count": row[
                "distinct_price_observation_dates"
            ],
            "price_observation_span_days": price_span_days,
            "current_price_available": row["current_price_min"] is not None,
        },
        "warnings": sorted(set(warnings)),
    }


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        return {
            "evaluated_items": 0,
            "min": None,
            "p25": None,
            "median": None,
            "mean": None,
            "p75": None,
            "p90": None,
            "max": None,
            "label_counts": {},
        }
    values = [item["score_raw"] for item in items]
    label_counts = {
        code: sum(item["label"]["code"] == code for item in items)
        for code in ("very_high", "high", "medium", "limited", "low", "very_low")
    }
    return {
        "evaluated_items": len(items),
        "min": round(min(values), 1),
        "p25": round(percentile(values, 0.25), 1),
        "median": round(percentile(values, 0.50), 1),
        "mean": round(fmean(values), 1),
        "p75": round(percentile(values, 0.75), 1),
        "p90": round(percentile(values, 0.90), 1),
        "max": round(max(values), 1),
        "label_counts": label_counts,
    }


def public_item(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if not key.endswith("_raw")}


def calculate(
    database_path: Path, as_of: datetime, item_id: int | None = None
) -> dict[str, Any]:
    calculated_at = iso_utc(datetime.now(timezone.utc))
    with closing(read_only_connection(database_path)) as connection:
        rows = connection.execute(AGGREGATE_SQL, (item_id, item_id)).fetchall()
    if item_id is not None and not rows:
        raise ConfidenceCalculationError("ITEM_NOT_FOUND")
    items = [calculate_item(row, as_of, calculated_at) for row in rows]
    return {
        "score_name": SCORE_NAME,
        "score_version": SCORE_VERSION,
        "calculated_at": calculated_at,
        "as_of": iso_utc(as_of),
        "summary": summarize(items),
        "items": [public_item(item) for item in items],
    }


def print_summary(result: dict[str, Any]) -> None:
    summary = result["summary"]
    print("DATA CONFIDENCE SCORE v0.1")
    print(f"Calculated at: {result['calculated_at']}")
    print(f"As of: {result['as_of']}")
    print(f"Evaluated items: {summary['evaluated_items']}")
    for key in ("min", "p25", "median", "mean", "p75", "p90", "max"):
        print(f"{key}: {summary[key]}")
    print("Labels:")
    for code, count in summary["label_counts"].items():
        print(f"  {code}: {count}")


def print_item(item: dict[str, Any]) -> None:
    print("DATA CONFIDENCE SCORE v0.1")
    for key in ("item_id", "score_name", "score_version", "calculated_at", "as_of"):
        print(f"{key}: {item[key]}")
    print(f"score: {item['score']}")
    print(f"label: {item['label']['en']} / {item['label']['ja']}")
    print("components:")
    for key, value in item["components"].items():
        print(f"  {key}: {value}")
    print("observation_stats:")
    for key, value in item["observation_stats"].items():
        print(f"  {key}: {value}")
    print("warnings:")
    if item["warnings"]:
        for warning in item["warnings"]:
            print(f"  {warning}")
    else:
        print("  none")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = SafeArgumentParser(
        description="Calculate read-only Data Confidence Score v0.1."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--item-id", type=positive_item_id)
    parser.add_argument("--as-of", type=parse_as_of)
    return parser.parse_args(argv)


def error_result(code: str) -> dict[str, str]:
    return {
        "score_name": SCORE_NAME,
        "score_version": SCORE_VERSION,
        "error": code,
    }


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    as_of = args.as_of or datetime.now(timezone.utc)
    try:
        result = calculate(args.db, as_of, args.item_id)
    except ConfidenceCalculationError as error:
        if args.json:
            print(json.dumps(error_result(str(error)), ensure_ascii=False))
        else:
            print(f"data confidence calculation failed: {error}", file=sys.stderr)
        return 2
    except (OSError, sqlite3.Error):
        if args.json:
            print(json.dumps(error_result("DATABASE_ACCESS_ERROR"), ensure_ascii=False))
        else:
            print(
                "data confidence calculation failed: DATABASE_ACCESS_ERROR",
                file=sys.stderr,
            )
        return 2
    except Exception:
        if args.json:
            print(json.dumps(error_result("UNEXPECTED_ERROR"), ensure_ascii=False))
        else:
            print("data confidence calculation failed: UNEXPECTED_ERROR", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    elif args.item_id is not None:
        print_item(result["items"][0])
    else:
        print_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
