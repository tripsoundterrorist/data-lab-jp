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


def load_env_value(name: str) -> str | None:
    prefix = f"{name}="
    for line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith(prefix):
            value = line[len(prefix) :].strip()
            return value or None
    return None


def safe_error(http_status: str, summary: str) -> None:
    print(f"HTTP status: {http_status}", file=sys.stderr)
    print(f"Error: {summary}", file=sys.stderr)


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


def json_state(value: str | None) -> str:
    if value is None:
        return "NULL"
    try:
        json.loads(value)
    except json.JSONDecodeError:
        return "invalid JSON"
    return "valid JSON"


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

    observed_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    collection_run_id = str(uuid.uuid4())
    query_context = {
        "site": "FANZA",
        "service": "digital",
        "floor": "videoa",
        "sort": "date",
        "hits": 1,
        "offset": 1,
    }
    request_parameters = {
        "api_id": api_id,
        "affiliate_id": affiliate_id,
        "site": query_context["site"],
        "service": query_context["service"],
        "floor": query_context["floor"],
        "sort": query_context["sort"],
        "hits": query_context["hits"],
        "offset": query_context["offset"],
        "output": "json",
    }
    request_url = (
        "https://api.dmm.com/affiliate/v3/ItemList?"
        + urllib.parse.urlencode(request_parameters)
    )

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        required_tables = {"items", "item_snapshots"}
        existing_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if not required_tables.issubset(existing_tables):
            safe_error("not requested", "先に init-db.py を実行してください。")
            return 1

        request = urllib.request.Request(
            request_url,
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
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

        items = result.get("items")
        if not isinstance(items, list) or not items or not isinstance(items[0], dict):
            safe_error(str(http_status), "The API returned no usable items.")
            return 1

        item = items[0]
        content_id = item.get("content_id")
        if not isinstance(content_id, str) or not content_id.strip():
            safe_error(str(http_status), "The item did not contain a content_id.")
            return 1

        prices = item.get("prices") if isinstance(item.get("prices"), dict) else {}
        review = item.get("review") if isinstance(item.get("review"), dict) else {}
        image_url = (
            item.get("imageURL") if isinstance(item.get("imageURL"), dict) else {}
        )
        price_raw = prices.get("price")
        price_raw = price_raw if isinstance(price_raw, str) else None
        maker_json = item_info_json(item, "maker")
        series_json = item_info_json(item, "series")
        actress_json = item_info_json(item, "actress")
        genre_json = item_info_json(item, "genre")

        with connection:
            connection.execute(
                """
                INSERT INTO items (
                  site, service, floor, content_id, product_id, title,
                  source_date, maker_json, series_json, actress_json, genre_json,
                  image_url_large, item_url, first_observed_at,
                  last_observed_at, master_updated_at
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
                    query_context["site"],
                    query_context["service"],
                    query_context["floor"],
                    content_id,
                    item.get("product_id"),
                    item.get("title"),
                    item.get("date"),
                    maker_json,
                    series_json,
                    actress_json,
                    genre_json,
                    image_url.get("large"),
                    item.get("URL"),
                    observed_at,
                    observed_at,
                    observed_at,
                ),
            )
            item_id = connection.execute(
                """
                SELECT id FROM items
                WHERE site = ? AND service = ? AND floor = ? AND content_id = ?
                """,
                (
                    query_context["site"],
                    query_context["service"],
                    query_context["floor"],
                    content_id,
                ),
            ).fetchone()["id"]
            connection.execute(
                """
                INSERT INTO item_snapshots (
                  item_id, collection_run_id, observed_at, source_sort,
                  source_offset, source_position, price_raw, price_min,
                  review_average, review_count, query_context_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    collection_run_id,
                    observed_at,
                    query_context["sort"],
                    query_context["offset"],
                    1,
                    price_raw,
                    parse_price_min(price_raw),
                    parse_optional_float(review.get("average")),
                    parse_optional_int(review.get("count")),
                    json.dumps(query_context, ensure_ascii=False, separators=(",", ":")),
                ),
            )

        stored = connection.execute(
            """
            SELECT
              i.content_id, i.product_id, i.title, i.source_date,
              i.maker_json, i.series_json, i.actress_json, i.genre_json,
              s.price_raw, s.price_min, s.review_average, s.review_count,
              s.observed_at, s.collection_run_id, s.source_offset,
              s.source_position
            FROM items AS i
            JOIN item_snapshots AS s ON s.item_id = i.id
            WHERE s.collection_run_id = ?
            """,
            (collection_run_id,),
        ).fetchone()

        print("api_communication: success")
        print(f"api_status: {result.get('status')}")
        print("upsert_result: success")
        print("snapshot_insert_result: success")
        print(f"items_count: {connection.execute('SELECT COUNT(*) FROM items').fetchone()[0]}")
        print(
            "item_snapshots_count: "
            f"{connection.execute('SELECT COUNT(*) FROM item_snapshots').fetchone()[0]}"
        )
        for field in (
            "content_id",
            "product_id",
            "title",
            "source_date",
            "price_raw",
            "price_min",
            "review_average",
            "review_count",
        ):
            print(f"{field}: {stored[field]}")
        print(f"maker_json: {json_state(stored['maker_json'])}")
        print(f"series_json: {json_state(stored['series_json'])}")
        print(f"actress_json: {json_state(stored['actress_json'])}")
        print(f"genre_json: {json_state(stored['genre_json'])}")
        for field in (
            "observed_at",
            "collection_run_id",
            "source_offset",
            "source_position",
        ):
            print(f"{field}: {stored[field]}")
        print(
            "foreign_key_check: "
            f"{len(connection.execute('PRAGMA foreign_key_check').fetchall())} violation(s)"
        )
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        safe_error("unavailable", "An unexpected error occurred.")
        raise SystemExit(1)
