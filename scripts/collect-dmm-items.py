from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
DATABASE_PATH = ROOT / "data" / "data-lab.db"
TIMEOUT_SECONDS = 15
HITS = 50
DEFAULT_MAX_ITEMS = 500
DEFAULT_MAX_PAGES = 10
MAX_ALLOWED_ITEMS = 5000
MAX_ALLOWED_PAGES = 100
REQUEST_INTERVAL_SECONDS = 1.0

BASE_QUERY_CONTEXT = {
    "site": "FANZA",
    "service": "digital",
    "floor": "videoa",
    "sort": "date",
}


def safe_error(http_status: str, summary: str) -> None:
    print(f"HTTP status: {http_status}", file=sys.stderr)
    print(f"Error: {summary}", file=sys.stderr)


class CollectionFailure(Exception):
    def __init__(
        self,
        stop_reason: str,
        error_code: str,
        http_status: str,
        summary: str,
    ) -> None:
        super().__init__(summary)
        self.stop_reason = stop_reason
        self.error_code = error_code
        self.http_status = http_status
        self.summary = summary


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def bounded_positive_integer(value: str, maximum: int) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"must be an integer from 1 to {maximum}"
        ) from error
    if parsed < 1 or parsed > maximum:
        raise argparse.ArgumentTypeError(
            f"must be an integer from 1 to {maximum}"
        )
    return parsed


def item_limit(value: str) -> int:
    return bounded_positive_integer(value, MAX_ALLOWED_ITEMS)


def page_limit(value: str) -> int:
    return bounded_positive_integer(value, MAX_ALLOWED_PAGES)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect DMM items using bounded automatic pagination."
    )
    parser.add_argument(
        "--max-items",
        type=item_limit,
        default=DEFAULT_MAX_ITEMS,
        help=f"maximum items to collect (default: {DEFAULT_MAX_ITEMS})",
    )
    parser.add_argument(
        "--max-pages",
        type=page_limit,
        default=DEFAULT_MAX_PAGES,
        help=f"maximum pages to collect (default: {DEFAULT_MAX_PAGES})",
    )
    return parser.parse_args(argv)


def load_env_value(name: str) -> str | None:
    prefix = f"{name}="
    for line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith(prefix):
            value = line[len(prefix) :].strip()
            return value or None
    return None


def item_info_json(item: dict[str, Any], field: str) -> str | None:
    item_info = item.get("iteminfo")
    if not isinstance(item_info, dict):
        return None

    value = item_info.get(field)
    if value is None:
        return None

    entries = value if isinstance(value, list) else [value]
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        normalized.append(
            {key: entry[key] for key in ("id", "name") if key in entry}
        )

    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def parse_price_min(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"([0-9]+)~?", value.strip())
    return int(match.group(1)) if match else None


def parse_optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if str(parsed) == str(value).strip() else None


def validate_database(connection: sqlite3.Connection) -> bool:
    required_tables = {"items", "item_snapshots", "collection_runs"}
    existing_tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    return required_tables.issubset(existing_tables)


def mark_run_failed(
    connection: sqlite3.Connection,
    collection_run_id: str,
    stop_reason: str,
    error_code: str,
    api_calls: int,
    pages_fetched: int,
    api_total_count_initial: int | None,
    total_count_changed: bool,
    fetched_items: int,
    duplicate_content_ids: int,
) -> None:
    try:
        with connection:
            connection.execute(
                """
                UPDATE collection_runs SET
                  finished_at = ?,
                  api_calls = ?,
                  pages_fetched = ?,
                  api_total_count_initial = ?,
                  total_count_changed = ?,
                  fetched_items = ?,
                  duplicate_content_ids_across_pages = ?,
                  collection_complete = 0,
                  status = 'failed',
                  stop_reason = ?,
                  error_code = ?
                WHERE collection_run_id = ?
                """,
                (
                    utc_now(),
                    api_calls,
                    pages_fetched,
                    api_total_count_initial,
                    int(total_count_changed),
                    fetched_items,
                    duplicate_content_ids,
                    stop_reason,
                    error_code,
                    collection_run_id,
                ),
            )
    except sqlite3.Error:
        # Do not expose database exception text or a traceback.
        pass


def main() -> int:
    args = parse_args()
    max_items = args.max_items
    max_pages = args.max_pages

    if not DATABASE_PATH.is_file():
        safe_error("not requested", "先に init-db.py を実行してください。")
        return 1

    if not ENV_PATH.is_file():
        safe_error("not requested", ".env was not found.")
        return 1

    api_id = load_env_value("DMM_API_ID")
    affiliate_id = load_env_value("DMM_AFFILIATE_ID")
    if not api_id or not affiliate_id:
        safe_error("not requested", "Required environment values are not configured.")
        return 1

    collection_run_id = str(uuid.uuid4())
    started_at = utc_now()
    observed_at = started_at
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    run_registered = False
    pages: list[dict[str, Any]] = []
    page_metrics: list[dict[str, int]] = []
    total_count_initial: int | None = None
    total_count_changed = False
    collection_complete = False
    stop_reason: str | None = None
    api_request_count = 0
    api_result_count = 0
    processed_count = 0
    upsert_count = 0
    snapshot_count = 0
    duplicate_content_ids: set[str] = set()

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        if not validate_database(connection):
            safe_error("not requested", "先に init-db.py を実行してください。")
            return 1

        with connection:
            connection.execute(
                """
                INSERT INTO collection_runs (
                  collection_run_id, run_type, started_at, site, service, floor,
                  source_sort, hits, max_items, max_pages, status
                ) VALUES (?, 'native', ?, ?, ?, ?, ?, ?, ?, ?, 'running')
                """,
                (
                    collection_run_id,
                    started_at,
                    BASE_QUERY_CONTEXT["site"],
                    BASE_QUERY_CONTEXT["service"],
                    BASE_QUERY_CONTEXT["floor"],
                    BASE_QUERY_CONTEXT["sort"],
                    HITS,
                    max_items,
                    max_pages,
                ),
            )
        run_registered = True

        # Complete and validate every HTTP request before starting database writes.
        offset = 1
        seen_content_ids: set[str] = set()

        while True:
            remaining_items = max_items - api_result_count
            request_hits = min(HITS, remaining_items)
            if request_hits <= 0:
                collection_complete = False
                stop_reason = "max_items"
                break

            query_context = {
                **BASE_QUERY_CONTEXT,
                "hits": request_hits,
                "offset": offset,
            }
            request_parameters = {
                "api_id": api_id,
                "affiliate_id": affiliate_id,
                **query_context,
                "output": "json",
            }
            request_url = (
                "https://api.dmm.com/affiliate/v3/ItemList?"
                + urllib.parse.urlencode(request_parameters)
            )
            request = urllib.request.Request(
                request_url,
                headers={"Accept": "application/json"},
                method="GET",
            )

            try:
                if api_request_count > 0:
                    time.sleep(REQUEST_INTERVAL_SECONDS)
                api_request_count += 1
                with urllib.request.urlopen(
                    request, timeout=TIMEOUT_SECONDS
                ) as response:
                    http_status = response.status
                    payload = json.load(response)
            except urllib.error.HTTPError as error:
                raise CollectionFailure(
                    "api_error",
                    "HTTP_ERROR",
                    str(error.code),
                    "The API returned a non-success response.",
                ) from None
            except (urllib.error.URLError, TimeoutError):
                raise CollectionFailure(
                    "api_error",
                    "API_REQUEST_FAILED",
                    "unavailable",
                    "The API request failed or timed out.",
                ) from None
            except json.JSONDecodeError:
                raise CollectionFailure(
                    "validation_error",
                    "INVALID_JSON",
                    "unavailable",
                    "The API response was not valid JSON.",
                ) from None

            result = payload.get("result") if isinstance(payload, dict) else None
            if not isinstance(result, dict) or str(result.get("status")) != "200":
                raise CollectionFailure(
                    "validation_error",
                    "INVALID_API_STATUS",
                    str(http_status),
                    "The API reported an unsuccessful status.",
                )

            response_items = result.get("items")
            if not isinstance(response_items, list):
                raise CollectionFailure(
                    "validation_error",
                    "INVALID_ITEMS",
                    str(http_status),
                    "The API did not return an items array.",
                )
            if any(not isinstance(item, dict) for item in response_items):
                raise CollectionFailure(
                    "validation_error",
                    "INVALID_ITEM_STRUCTURE",
                    str(http_status),
                    "The API returned an invalid item structure.",
                )

            page_result_count = parse_optional_int(result.get("result_count"))
            page_total_count = parse_optional_int(result.get("total_count"))
            if (
                page_result_count is None
                or page_result_count < 0
                or page_result_count != len(response_items)
                or page_result_count > request_hits
            ):
                raise CollectionFailure(
                    "validation_error",
                    "INVALID_RESULT_COUNT",
                    str(http_status),
                    "The API returned an invalid result count.",
                )
            if page_total_count is None or page_total_count < 0:
                raise CollectionFailure(
                    "validation_error",
                    "INVALID_TOTAL_COUNT",
                    str(http_status),
                    "The API returned an invalid total count.",
                )

            page_content_ids: list[str] = []
            for item in response_items:
                content_id = item.get("content_id")
                if not isinstance(content_id, str) or not content_id.strip():
                    raise CollectionFailure(
                        "validation_error",
                        "INVALID_CONTENT_ID",
                        str(http_status),
                        "An item did not contain a usable content_id.",
                    )
                page_content_ids.append(content_id)

            if total_count_initial is None:
                total_count_initial = page_total_count
            elif page_total_count != total_count_initial:
                total_count_changed = True

            duplicate_content_ids.update(set(page_content_ids) & seen_content_ids)
            seen_content_ids.update(page_content_ids)

            pages.append(
                {
                    "offset": offset,
                    "items": response_items,
                    "query_context_json": json.dumps(
                        query_context, ensure_ascii=False, separators=(",", ":")
                    ),
                }
            )
            page_metrics.append(
                {
                    "offset": offset,
                    "result_count": page_result_count,
                    "total_count": page_total_count,
                }
            )
            api_result_count += page_result_count

            if api_result_count >= max_items:
                collection_complete = False
                stop_reason = "max_items"
                break
            if len(pages) >= max_pages:
                collection_complete = False
                stop_reason = "max_pages"
                break
            if page_result_count < request_hits:
                collection_complete = True
                stop_reason = "api_end"
                break

            # DMM offset is the one-based result start position. Because this
            # branch is reached only for a full page, advancing by the actual
            # requested page size starts immediately after the current page.
            next_offset = offset + request_hits
            if next_offset > page_total_count:
                collection_complete = True
                stop_reason = "api_end"
                break
            offset = next_offset

        processed_count = 0
        upsert_count = 0
        snapshot_count = 0

        with connection:
            work_items = (
                (
                    page["offset"],
                    page["query_context_json"],
                    source_position,
                    item,
                )
                for page in pages
                for source_position, item in enumerate(page["items"], start=1)
            )
            for source_offset, query_context_json, source_position, item in work_items:
                content_id = item.get("content_id")
                if not isinstance(content_id, str) or not content_id.strip():
                    raise ValueError("An item did not contain a usable content_id.")

                prices = (
                    item.get("prices")
                    if isinstance(item.get("prices"), dict)
                    else {}
                )
                review = (
                    item.get("review")
                    if isinstance(item.get("review"), dict)
                    else {}
                )
                image_url = (
                    item.get("imageURL")
                    if isinstance(item.get("imageURL"), dict)
                    else {}
                )
                price_raw = prices.get("price")
                price_raw = price_raw if isinstance(price_raw, str) else None

                connection.execute(
                    """
                    INSERT INTO items (
                      site, service, floor, content_id, product_id, title,
                      source_date, maker_json, series_json, actress_json,
                      genre_json, image_url_large, item_url,
                      first_observed_at, last_observed_at, master_updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (site, service, floor, content_id) DO UPDATE SET
                      master_updated_at = CASE
                        WHEN items.product_id IS NOT excluded.product_id
                          OR items.title IS NOT excluded.title
                          OR items.source_date IS NOT excluded.source_date
                          OR items.maker_json IS NOT excluded.maker_json
                          OR items.series_json IS NOT excluded.series_json
                          OR items.actress_json IS NOT excluded.actress_json
                          OR items.genre_json IS NOT excluded.genre_json
                          OR items.image_url_large IS NOT excluded.image_url_large
                          OR items.item_url IS NOT excluded.item_url
                        THEN excluded.master_updated_at
                        ELSE items.master_updated_at
                      END,
                      product_id = excluded.product_id,
                      title = excluded.title,
                      source_date = excluded.source_date,
                      maker_json = excluded.maker_json,
                      series_json = excluded.series_json,
                      actress_json = excluded.actress_json,
                      genre_json = excluded.genre_json,
                      image_url_large = excluded.image_url_large,
                      item_url = excluded.item_url,
                      last_observed_at = excluded.last_observed_at
                    """,
                    (
                        BASE_QUERY_CONTEXT["site"],
                        BASE_QUERY_CONTEXT["service"],
                        BASE_QUERY_CONTEXT["floor"],
                        content_id,
                        item.get("product_id"),
                        item.get("title"),
                        item.get("date"),
                        item_info_json(item, "maker"),
                        item_info_json(item, "series"),
                        item_info_json(item, "actress"),
                        item_info_json(item, "genre"),
                        image_url.get("large"),
                        item.get("URL"),
                        observed_at,
                        observed_at,
                        observed_at,
                    ),
                )
                upsert_count += 1

                item_row = connection.execute(
                    """
                    SELECT id FROM items
                    WHERE site = ? AND service = ? AND floor = ? AND content_id = ?
                    """,
                    (
                        BASE_QUERY_CONTEXT["site"],
                        BASE_QUERY_CONTEXT["service"],
                        BASE_QUERY_CONTEXT["floor"],
                        content_id,
                    ),
                ).fetchone()
                if item_row is None:
                    raise RuntimeError("The stored item could not be resolved.")

                connection.execute(
                    """
                    INSERT INTO item_snapshots (
                      item_id, collection_run_id, observed_at, source_sort,
                      source_offset, source_position, price_raw, price_min,
                      review_average, review_count, query_context_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item_row["id"],
                        collection_run_id,
                        observed_at,
                        BASE_QUERY_CONTEXT["sort"],
                        source_offset,
                        source_position,
                        price_raw,
                        parse_price_min(price_raw),
                        parse_optional_float(review.get("average")),
                        parse_optional_int(review.get("count")),
                        query_context_json,
                    ),
                )
                snapshot_count += 1
                processed_count += 1

            if stop_reason is None:
                raise RuntimeError("The collection stop reason was not determined.")

            connection.execute(
                """
                UPDATE collection_runs SET
                  finished_at = ?,
                  first_observed_at = ?,
                  last_observed_at = ?,
                  api_calls = ?,
                  pages_fetched = ?,
                  api_total_count_initial = ?,
                  total_count_changed = ?,
                  fetched_items = ?,
                  processed_items = ?,
                  duplicate_content_ids_across_pages = ?,
                  items_upserted = ?,
                  snapshots_inserted = ?,
                  collection_complete = ?,
                  status = 'success',
                  stop_reason = ?,
                  error_code = NULL
                WHERE collection_run_id = ?
                """,
                (
                    utc_now(),
                    observed_at,
                    observed_at,
                    api_request_count,
                    len(page_metrics),
                    total_count_initial,
                    int(total_count_changed),
                    api_result_count,
                    processed_count,
                    len(duplicate_content_ids),
                    upsert_count,
                    snapshot_count,
                    int(collection_complete),
                    stop_reason,
                    collection_run_id,
                ),
            )

        print("api_status: 200")
        print(f"api_calls: {api_request_count}")
        print(f"pages_fetched: {len(page_metrics)}")
        print(f"api_total_count_initial: {total_count_initial}")
        print(f"total_count_changed: {json.dumps(total_count_changed)}")
        print(f"fetched_items: {api_result_count}")
        print(f"processed_items: {processed_count}")
        print(f"duplicate_content_ids_across_pages: {len(duplicate_content_ids)}")
        print(f"items_upserted: {upsert_count}")
        print(f"snapshots_inserted: {snapshot_count}")
        print(f"collection_run_id: {collection_run_id}")
        print(f"observed_at: {observed_at}")
        print(f"collection_complete: {json.dumps(collection_complete)}")
        return 0
    except CollectionFailure as failure:
        if run_registered:
            mark_run_failed(
                connection,
                collection_run_id,
                failure.stop_reason,
                failure.error_code,
                api_request_count,
                len(page_metrics),
                total_count_initial,
                total_count_changed,
                api_result_count,
                len(duplicate_content_ids),
            )
        safe_error(failure.http_status, failure.summary)
        return 1
    except sqlite3.Error:
        if run_registered:
            mark_run_failed(
                connection,
                collection_run_id,
                "db_error",
                "DB_OPERATION_FAILED",
                api_request_count,
                len(page_metrics),
                total_count_initial,
                total_count_changed,
                api_result_count,
                len(duplicate_content_ids),
            )
        safe_error("unavailable", "A database operation failed.")
        return 1
    except Exception:
        if run_registered:
            mark_run_failed(
                connection,
                collection_run_id,
                "unexpected_error",
                "UNEXPECTED_ERROR",
                api_request_count,
                len(page_metrics),
                total_count_initial,
                total_count_changed,
                api_result_count,
                len(duplicate_content_ids),
            )
        safe_error("unavailable", "An unexpected error occurred.")
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        safe_error("unavailable", "An unexpected error occurred; the collection was rolled back.")
        raise SystemExit(1)
