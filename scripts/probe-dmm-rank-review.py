"""Bounded, read-only FANZA rank/review API probe.

The probe emits aggregate metrics only. It never persists API responses,
credentials, URLs, titles, content IDs, or database changes.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
DATABASE_PATH = ROOT / "data" / "data-lab.db"
ENDPOINT = "https://api.dmm.com/affiliate/v3/ItemList"
SORTS = ("rank", "review")
HITS = 100
OFFSET = 1
TIMEOUT_SECONDS = 20
REQUEST_INTERVAL_SECONDS = 1.0


class ProbeFailure(Exception):
    def __init__(self, code: str, *, rate_limited: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.rate_limited = rate_limited


@dataclass(frozen=True)
class DatabasePopulation:
    all_content_ids: frozenset[str]
    date_content_ids: frozenset[str]


@dataclass(frozen=True)
class ProbeResult:
    source_sort: str
    http_success: bool
    api_success: bool
    result_count: int
    total_count: int
    returned_count: int
    elapsed_ms: int
    content_ids: frozenset[str]
    duplicate_content_id_count: int
    coverage: dict[str, dict[str, int | float]]
    review: dict[str, Any]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run two bounded, aggregate-only DMM API probes."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate local prerequisites without making API requests",
    )
    return parser.parse_args(argv)


def load_env_value(name: str) -> str | None:
    """Use the collector's exact-name dotenv convention without dumping it."""

    prefix = f"{name}="
    for line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith(prefix):
            value = line[len(prefix) :].strip()
            return value or None
    return None


def read_database_population(path: Path) -> DatabasePopulation:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        all_ids = frozenset(
            str(row[0])
            for row in connection.execute(
                """
                SELECT content_id FROM items
                WHERE site = 'FANZA' AND service = 'digital' AND floor = 'videoa'
                """
            )
        )
        date_ids = frozenset(
            str(row[0])
            for row in connection.execute(
                """
                SELECT DISTINCT i.content_id
                FROM item_snapshots AS s
                JOIN items AS i ON i.id = s.item_id
                WHERE i.site = 'FANZA'
                  AND i.service = 'digital'
                  AND i.floor = 'videoa'
                  AND s.source_sort = 'date'
                """
            )
        )
        return DatabasePopulation(all_ids, date_ids)
    finally:
        connection.close()


def optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if str(parsed) == str(value).strip() else None


def optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def nested(item: dict[str, Any], *path: str) -> Any:
    value: Any = item
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def any_iteminfo(item: dict[str, Any], field: str) -> bool:
    return present(nested(item, "iteminfo", field))


def rate_limit_hint(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.lower().replace("_", " ").replace("-", " ")
    return any(token in normalized for token in ("rate limit", "too many request"))


def numeric_summary(values: Iterable[int | float]) -> dict[str, int | float | None]:
    data = list(values)
    if not data:
        return {"min": None, "median": None, "mean": None, "max": None}
    return {
        "min": min(data),
        "median": statistics.median(data),
        "mean": round(statistics.fmean(data), 4),
        "max": max(data),
    }


def coverage_metric(count: int, total: int) -> dict[str, int | float]:
    return {
        "count": count,
        "percent": round((count / total * 100.0) if total else 0.0, 2),
    }


def analyze(source_sort: str, payload: Any, http_status: int, elapsed_ms: int) -> ProbeResult:
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        raise ProbeFailure("INVALID_RESULT_OBJECT")
    api_status = str(result.get("status"))
    if api_status != "200":
        raise ProbeFailure(
            "API_STATUS_ERROR",
            rate_limited=(api_status == "429" or rate_limit_hint(result.get("message"))),
        )
    items = result.get("items")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ProbeFailure("INVALID_ITEMS")
    result_count = optional_int(result.get("result_count"))
    total_count = optional_int(result.get("total_count"))
    if (
        result_count is None
        or total_count is None
        or result_count < 0
        or total_count < 0
        or result_count != len(items)
        or result_count > HITS
    ):
        raise ProbeFailure("INVALID_COUNTS")

    ids = [item.get("content_id") for item in items]
    valid_ids = [value.strip() for value in ids if isinstance(value, str) and value.strip()]
    content_ids = frozenset(valid_ids)
    field_checks = {
        "content_id": lambda item: present(item.get("content_id")),
        "product_id": lambda item: present(item.get("product_id")),
        "price": lambda item: present(nested(item, "prices", "price")),
        "source_date": lambda item: present(item.get("date")),
        "review.average": lambda item: optional_float(nested(item, "review", "average")) is not None,
        "review.count": lambda item: optional_int(nested(item, "review", "count")) is not None,
        "maker": lambda item: any_iteminfo(item, "maker"),
        "series": lambda item: any_iteminfo(item, "series"),
        "actress": lambda item: any_iteminfo(item, "actress"),
        "genre": lambda item: any_iteminfo(item, "genre"),
        "image_url": lambda item: present(item.get("imageURL")),
        "item_url": lambda item: present(item.get("URL")),
    }
    coverage = {
        field: coverage_metric(sum(1 for item in items if check(item)), len(items))
        for field, check in field_checks.items()
    }

    averages = [
        value
        for item in items
        if (value := optional_float(nested(item, "review", "average"))) is not None
    ]
    counts = [
        value
        for item in items
        if (value := optional_int(nested(item, "review", "count"))) is not None
    ]
    average_present = [optional_float(nested(item, "review", "average")) is not None for item in items]
    count_present = [optional_int(nested(item, "review", "count")) is not None for item in items]
    both = sum(a and c for a, c in zip(average_present, count_present))
    average_only = sum(a and not c for a, c in zip(average_present, count_present))
    count_only = sum(not a and c for a, c in zip(average_present, count_present))
    neither = len(items) - both - average_only - count_only
    review = {
        "average_present": coverage_metric(sum(average_present), len(items)),
        "count_present": coverage_metric(sum(count_present), len(items)),
        "both_present": coverage_metric(both, len(items)),
        "average_only": average_only,
        "count_only": count_only,
        "neither": neither,
        "review_count_distribution": numeric_summary(counts),
        "review_average_distribution": numeric_summary(averages),
    }
    return ProbeResult(
        source_sort=source_sort,
        http_success=(200 <= http_status < 300),
        api_success=True,
        result_count=result_count,
        total_count=total_count,
        returned_count=len(items),
        elapsed_ms=elapsed_ms,
        content_ids=content_ids,
        duplicate_content_id_count=len(valid_ids) - len(content_ids),
        coverage=coverage,
        review=review,
    )


def request_probe(source_sort: str, api_id: str, affiliate_id: str) -> ProbeResult:
    parameters = {
        "api_id": api_id,
        "affiliate_id": affiliate_id,
        "site": "FANZA",
        "service": "digital",
        "floor": "videoa",
        "sort": source_sort,
        "hits": HITS,
        "offset": OFFSET,
        "output": "json",
    }
    request = urllib.request.Request(
        ENDPOINT + "?" + urllib.parse.urlencode(parameters),
        headers={"Accept": "application/json"},
        method="GET",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        raise ProbeFailure("HTTP_ERROR", rate_limited=(error.code == 429)) from None
    except (urllib.error.URLError, TimeoutError):
        raise ProbeFailure("REQUEST_FAILED") from None
    except json.JSONDecodeError:
        raise ProbeFailure("INVALID_JSON") from None
    elapsed_ms = round((time.monotonic() - started) * 1000)
    return analyze(source_sort, payload, status, elapsed_ms)


def safe_result(result: ProbeResult, population: DatabasePopulation) -> dict[str, Any]:
    return {
        "sort": result.source_sort,
        "http_success": result.http_success,
        "api_success": result.api_success,
        "result_count": result.result_count,
        "total_count": result.total_count,
        "returned_count": result.returned_count,
        "elapsed_ms": result.elapsed_ms,
        "duplicate_content_id_count": result.duplicate_content_id_count,
        "coverage": result.coverage,
        "review": result.review,
        "population_overlap": {
            "production_items_count": len(result.content_ids & population.all_content_ids),
            "date_observed_count": len(result.content_ids & population.date_content_ids),
        },
    }


def comparison(rank: ProbeResult, review: ProbeResult) -> dict[str, int | float]:
    overlap = rank.content_ids & review.content_ids
    union = rank.content_ids | review.content_ids
    return {
        "overlap_count": len(overlap),
        "overlap_percent_of_rank": round(len(overlap) / len(rank.content_ids) * 100, 2) if rank.content_ids else 0.0,
        "overlap_percent_of_review": round(len(overlap) / len(review.content_ids) * 100, 2) if review.content_ids else 0.0,
        "jaccard_percent": round(len(overlap) / len(union) * 100, 2) if union else 0.0,
        "rank_only_count": len(rank.content_ids - review.content_ids),
        "review_only_count": len(review.content_ids - rank.content_ids),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        population = read_database_population(DATABASE_PATH)
        api_id = load_env_value("DMM_API_ID")
        affiliate_id = load_env_value("DMM_AFFILIATE_ID")
        if not api_id or not affiliate_id:
            raise ProbeFailure("CREDENTIALS_NOT_CONFIGURED")
        if args.dry_run:
            print(json.dumps({
                "probe_status": "dry_run_ready",
                "api_calls": 0,
                "planned_sorts": list(SORTS),
                "hits": HITS,
                "offset": OFFSET,
                "database_mode": "read_only",
                "production_population_count": len(population.all_content_ids),
                "date_observed_population_count": len(population.date_content_ids),
            }, separators=(",", ":")))
            return 0

        results: list[ProbeResult] = []
        for index, source_sort in enumerate(SORTS):
            if index:
                time.sleep(REQUEST_INTERVAL_SECONDS)
            try:
                results.append(request_probe(source_sort, api_id, affiliate_id))
            except ProbeFailure as error:
                print(json.dumps({
                    "probe_status": "failed",
                    "api_calls": index + 1,
                    "failed_sort": source_sort,
                    "error_code": error.code,
                    "rate_limited": error.rate_limited,
                    "stopped_without_retry": True,
                }, separators=(",", ":")), file=sys.stderr)
                return 2

        rank, review = results
        print(json.dumps({
            "probe_status": "success",
            "api_calls": 2,
            "query_position_semantics": "rank-sorted observation position",
            "review_population_semantics": "review-sorted population",
            "probes": [safe_result(result, population) for result in results],
            "population_comparison": comparison(rank, review),
        }, separators=(",", ":")))
        return 0
    except (OSError, sqlite3.Error):
        print('{"probe_status":"failed","api_calls":0,"error_code":"LOCAL_PREREQUISITE_ERROR"}', file=sys.stderr)
        return 3
    except ProbeFailure as error:
        print(json.dumps({
            "probe_status": "failed",
            "api_calls": 0,
            "error_code": error.code,
            "rate_limited": error.rate_limited,
        }, separators=(",", ":")), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
