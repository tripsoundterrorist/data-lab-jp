from __future__ import annotations

import json
import re
import sqlite3
import sys
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

BASE_QUERY_CONTEXT = {
    "site": "FANZA",
    "service": "digital",
    "floor": "videoa",
    "sort": "date",
    "hits": 50,
}
OFFSETS = (1, 51)
# Future automatic paging: after the first response supplies total_count,
# generate subsequent offsets with range(1, total_count + 1, hits).


def safe_error(http_status: str, summary: str) -> None:
    print(f"HTTP status: {http_status}", file=sys.stderr)
    print(f"Error: {summary}", file=sys.stderr)


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
    required_tables = {"items", "item_snapshots"}
    existing_tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    return required_tables.issubset(existing_tables)


def main() -> int:
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
    observed_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        if not validate_database(connection):
            safe_error("not requested", "先に init-db.py を実行してください。")
            return 1

        # Complete and validate every HTTP request before starting database writes.
        pages: list[dict[str, Any]] = []
        total_count: int | None = None
        api_request_count = 0
        api_result_count = 0

        for offset in OFFSETS:
            if total_count is not None and offset > total_count:
                break

            query_context = {**BASE_QUERY_CONTEXT, "offset": offset}
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
                api_request_count += 1
                with urllib.request.urlopen(
                    request, timeout=TIMEOUT_SECONDS
                ) as response:
                    http_status = response.status
                    payload = json.load(response)
            except urllib.error.HTTPError as error:
                safe_error(str(error.code), "The API returned a non-success response.")
                return 1
            except (urllib.error.URLError, TimeoutError):
                safe_error("unavailable", "The API request failed or timed out.")
                return 1
            except json.JSONDecodeError:
                safe_error("unavailable", "The API response was not valid JSON.")
                return 1

            result = payload.get("result") if isinstance(payload, dict) else None
            if not isinstance(result, dict) or str(result.get("status")) != "200":
                safe_error(str(http_status), "The API reported an unsuccessful status.")
                return 1

            response_items = result.get("items")
            if not isinstance(response_items, list):
                safe_error(str(http_status), "The API did not return an items array.")
                return 1
            if any(not isinstance(item, dict) for item in response_items):
                safe_error(str(http_status), "The API returned an invalid item structure.")
                return 1

            page_result_count = parse_optional_int(result.get("result_count"))
            page_total_count = parse_optional_int(result.get("total_count"))
            if (
                page_result_count is None
                or page_result_count < 0
                or page_result_count != len(response_items)
                or page_result_count > BASE_QUERY_CONTEXT["hits"]
            ):
                safe_error(str(http_status), "The API returned an invalid result count.")
                return 1
            if page_total_count is None or page_total_count < 0:
                safe_error(str(http_status), "The API returned an invalid total count.")
                return 1

            if total_count is None:
                total_count = page_total_count

            pages.append(
                {
                    "offset": offset,
                    "items": response_items,
                    "query_context_json": json.dumps(
                        query_context, ensure_ascii=False, separators=(",", ":")
                    ),
                }
            )
            api_result_count += page_result_count

            if page_result_count < BASE_QUERY_CONTEXT["hits"]:
                break

        if not pages or api_result_count == 0:
            safe_error("200", "The API returned no usable items.")
            return 1

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

        print("api_status: 200")
        print(f"api_request_count: {api_request_count}")
        print(f"api_total_count: {total_count}")
        print(f"api_result_count: {api_result_count}")
        print(f"processed_count: {processed_count}")
        print(f"items_upserted: {upsert_count}")
        print(f"snapshots_inserted: {snapshot_count}")
        print(f"collection_run_id: {collection_run_id}")
        print(f"observed_at: {observed_at}")
        print("error: none")
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        safe_error("unavailable", "An unexpected error occurred; the collection was rolled back.")
        raise SystemExit(1)
