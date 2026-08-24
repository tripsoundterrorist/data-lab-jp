"""Four-request, aggregate-only rank/review reproducibility probe.

This script reuses v0.1's safe parsing and database population helpers without
changing v0.1. API responses and identifiers remain memory-only.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
BASE_PROBE_PATH = ROOT / "scripts" / "probe-dmm-rank-review.py"
DATABASE_PATH = ROOT / "data" / "data-lab.db"
REQUESTS = (("rank", 1), ("rank", 101), ("review", 1), ("review", 101))
HITS = 100
REQUEST_INTERVAL_SECONDS = 1.0


def load_base_probe() -> Any:
    specification = importlib.util.spec_from_file_location(
        "rank_review_probe_v01", BASE_PROBE_PATH
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("base probe unavailable")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


base = load_base_probe()


@dataclass(frozen=True)
class ReproPage:
    source_sort: str
    offset: int
    result: Any
    first_position: int | None
    ordering_anomaly: bool
    thresholds: dict[str, dict[str, int | float]]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run four fixed, aggregate-only reproducibility probes."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate prerequisites without making API requests",
    )
    return parser.parse_args(argv)


def metric(count: int, total: int) -> dict[str, int | float]:
    return {
        "count": count,
        "percent": round(count / total * 100.0, 2) if total else 0.0,
    }


def page_thresholds(items: list[dict[str, Any]]) -> dict[str, dict[str, int | float]]:
    averages = [
        base.optional_float(base.nested(item, "review", "average"))
        for item in items
    ]
    counts = [
        base.optional_int(base.nested(item, "review", "count"))
        for item in items
    ]
    return {
        "average_equals_5_0": metric(sum(value == 5.0 for value in averages), len(items)),
        "average_at_least_4_5": metric(
            sum(value is not None and value >= 4.5 for value in averages), len(items)
        ),
        "review_count_at_least_10": metric(
            sum(value is not None and value >= 10 for value in counts), len(items)
        ),
        "review_count_at_least_50": metric(
            sum(value is not None and value >= 50 for value in counts), len(items)
        ),
    }


def request_page(
    source_sort: str, offset: int, api_id: str, affiliate_id: str
) -> ReproPage:
    parameters = {
        "api_id": api_id,
        "affiliate_id": affiliate_id,
        "site": "FANZA",
        "service": "digital",
        "floor": "videoa",
        "sort": source_sort,
        "hits": HITS,
        "offset": offset,
        "output": "json",
    }
    request = urllib.request.Request(
        base.ENDPOINT + "?" + urllib.parse.urlencode(parameters),
        headers={"Accept": "application/json"},
        method="GET",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=base.TIMEOUT_SECONDS) as response:
            status = response.status
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        raise base.ProbeFailure(
            "HTTP_ERROR", rate_limited=(error.code == 429)
        ) from None
    except (urllib.error.URLError, TimeoutError):
        raise base.ProbeFailure("REQUEST_FAILED") from None
    except json.JSONDecodeError:
        raise base.ProbeFailure("INVALID_JSON") from None

    elapsed_ms = round((time.monotonic() - started) * 1000)
    result = base.analyze(source_sort, payload, status, elapsed_ms)
    result_object = payload.get("result") if isinstance(payload, dict) else None
    items = result_object.get("items") if isinstance(result_object, dict) else None
    if not isinstance(items, list):
        raise base.ProbeFailure("INVALID_ITEMS")
    first_position = base.optional_int(result_object.get("first_position"))
    return ReproPage(
        source_sort=source_sort,
        offset=offset,
        result=result,
        first_position=first_position,
        ordering_anomaly=(
            first_position != offset or result.duplicate_content_id_count != 0
        ),
        thresholds=page_thresholds(items),
    )


def safe_page(page: ReproPage, population: Any) -> dict[str, Any]:
    summary = base.safe_result(page.result, population)
    summary["offset"] = page.offset
    summary["first_position"] = page.first_position
    summary["ordering_anomaly"] = page.ordering_anomaly
    summary["review_thresholds"] = page.thresholds
    return summary


def pair_comparison(
    left: ReproPage, right: ReproPage, *, expect_disjoint: bool
) -> dict[str, int | float | bool]:
    left_ids = left.result.content_ids
    right_ids = right.result.content_ids
    overlap = left_ids & right_ids
    union = left_ids | right_ids
    return {
        "overlap_count": len(overlap),
        "overlap_percent_of_left": round(len(overlap) / len(left_ids) * 100, 2) if left_ids else 0.0,
        "overlap_percent_of_right": round(len(overlap) / len(right_ids) * 100, 2) if right_ids else 0.0,
        "jaccard_percent": round(len(overlap) / len(union) * 100, 2) if union else 0.0,
        "left_only_count": len(left_ids - right_ids),
        "right_only_count": len(right_ids - left_ids),
        "left_page_duplicate_count": left.result.duplicate_content_id_count,
        "right_page_duplicate_count": right.result.duplicate_content_id_count,
        "cross_page_overlap_anomaly": bool(overlap) if expect_disjoint else False,
        "ordering_anomaly": left.ordering_anomaly or right.ordering_anomaly,
    }


def union_comparison(rank_pages: list[ReproPage], review_pages: list[ReproPage]) -> dict[str, int | float]:
    rank_ids = frozenset().union(*(page.result.content_ids for page in rank_pages))
    review_ids = frozenset().union(*(page.result.content_ids for page in review_pages))
    overlap = rank_ids & review_ids
    union = rank_ids | review_ids
    return {
        "rank_union_count": len(rank_ids),
        "review_union_count": len(review_ids),
        "overlap_count": len(overlap),
        "overlap_percent_of_rank": round(len(overlap) / len(rank_ids) * 100, 2) if rank_ids else 0.0,
        "overlap_percent_of_review": round(len(overlap) / len(review_ids) * 100, 2) if review_ids else 0.0,
        "jaccard_percent": round(len(overlap) / len(union) * 100, 2) if union else 0.0,
        "rank_only_count": len(rank_ids - review_ids),
        "review_only_count": len(review_ids - rank_ids),
    }


def date_overlaps(pages: list[ReproPage], date_ids: frozenset[str]) -> dict[str, int]:
    rank_pages = [page for page in pages if page.source_sort == "rank"]
    review_pages = [page for page in pages if page.source_sort == "review"]
    rank_union = frozenset().union(*(page.result.content_ids for page in rank_pages))
    review_union = frozenset().union(*(page.result.content_ids for page in review_pages))
    return {
        "rank_offset_1": len(rank_pages[0].result.content_ids & date_ids),
        "rank_offset_101": len(rank_pages[1].result.content_ids & date_ids),
        "rank_union": len(rank_union & date_ids),
        "review_offset_1": len(review_pages[0].result.content_ids & date_ids),
        "review_offset_101": len(review_pages[1].result.content_ids & date_ids),
        "review_union": len(review_union & date_ids),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        population = base.read_database_population(DATABASE_PATH)
        api_id = base.load_env_value("DMM_API_ID")
        affiliate_id = base.load_env_value("DMM_AFFILIATE_ID")
        if not api_id or not affiliate_id:
            raise base.ProbeFailure("CREDENTIALS_NOT_CONFIGURED")
        if args.dry_run:
            print(json.dumps({
                "probe_status": "dry_run_ready",
                "api_calls": 0,
                "planned_requests": [
                    {"sort": source_sort, "offset": offset, "hits": HITS}
                    for source_sort, offset in REQUESTS
                ],
                "database_mode": "read_only",
                "date_observed_population_count": len(population.date_content_ids),
            }, separators=(",", ":")))
            return 0

        pages: list[ReproPage] = []
        for index, (source_sort, offset) in enumerate(REQUESTS):
            if index:
                time.sleep(REQUEST_INTERVAL_SECONDS)
            try:
                pages.append(request_page(source_sort, offset, api_id, affiliate_id))
            except base.ProbeFailure as error:
                print(json.dumps({
                    "probe_status": "failed",
                    "api_calls": index + 1,
                    "failed_request": {"sort": source_sort, "offset": offset},
                    "error_code": error.code,
                    "rate_limited": error.rate_limited,
                    "stopped_without_retry": True,
                }, separators=(",", ":")), file=sys.stderr)
                return 2

        rank_pages = [page for page in pages if page.source_sort == "rank"]
        review_pages = [page for page in pages if page.source_sort == "review"]
        print(json.dumps({
            "probe_status": "success",
            "api_calls": 4,
            "position_semantics": "API response position; not a global rank",
            "review_population_semantics": "review-sorted population",
            "total_count_semantics": "API-reported count; not asserted as market size",
            "pages": [safe_page(page, population) for page in pages],
            "page_comparison": {
                "rank_offset_1_vs_101": pair_comparison(
                    *rank_pages, expect_disjoint=True
                ),
                "review_offset_1_vs_101": pair_comparison(
                    *review_pages, expect_disjoint=True
                ),
            },
            "rank_review_pairs": {
                f"rank_{rank.offset}_vs_review_{review.offset}": pair_comparison(
                    rank, review, expect_disjoint=False
                )
                for rank in rank_pages
                for review in review_pages
            },
            "rank_union_vs_review_union": union_comparison(rank_pages, review_pages),
            "date_population_overlap": date_overlaps(pages, population.date_content_ids),
        }, separators=(",", ":")))
        return 0
    except (OSError, sqlite3.Error, RuntimeError):
        print('{"probe_status":"failed","api_calls":0,"error_code":"LOCAL_PREREQUISITE_ERROR"}', file=sys.stderr)
        return 3
    except base.ProbeFailure as error:
        print(json.dumps({
            "probe_status": "failed",
            "api_calls": 0,
            "error_code": error.code,
            "rate_limited": error.rate_limited,
        }, separators=(",", ":")), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
