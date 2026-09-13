from __future__ import annotations

import argparse
import copy
import hashlib
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

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "category-collection-v0.1.json"
SCHEMA_PATH = ROOT / "db" / "category-collection-schema.sql"
DATABASE_PATH = ROOT / "data" / "category-collection.db"
ENV_PATH = ROOT / ".env"
ENDPOINT = "https://api.dmm.com/affiliate/v3/ItemList"
NORMALIZER_VERSION = "0.1"
ALLOWED_KEYS = {"version", "mode", "targets"}
REQUIRED_TARGET_KEYS = {"content_type", "site", "service", "floor"}
SENSITIVE_KEY_TOKENS = {
    "affiliateurl", "affiliateid", "apiid", "authorization", "credential",
    "password", "secret", "token",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_secret(name: str) -> str | None:
    if not ENV_PATH.is_file():
        return None
    prefix = name + "="
    for line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip() or None
    return None


def load_config(path: Path = CONFIG_PATH) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != ALLOWED_KEYS:
        raise ValueError("CONFIG_SHAPE_INVALID")
    if data.get("version") != "0.1" or data.get("mode") != "COLLECTION_ONLY":
        raise ValueError("CONFIG_MODE_INVALID")
    targets = data.get("targets")
    if not isinstance(targets, list) or not targets:
        raise ValueError("CONFIG_TARGETS_INVALID")
    identities: set[tuple[str, str, str]] = set()
    content_types: set[str] = set()
    for target in targets:
        if not isinstance(target, dict) or set(target) != REQUIRED_TARGET_KEYS:
            raise ValueError("CONFIG_TARGET_INVALID")
        if not all(isinstance(target[k], str) and target[k] for k in REQUIRED_TARGET_KEYS):
            raise ValueError("CONFIG_TARGET_VALUE_INVALID")
        identity = (target["site"], target["service"], target["floor"])
        if identity in identities or target["content_type"] in content_types:
            raise ValueError("CONFIG_TARGET_DUPLICATE")
        identities.add(identity)
        content_types.add(target["content_type"])
    return targets


def sanitize_raw(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: sanitize_raw(v) for k, v in value.items()
            if not sensitive_key(k)
        }
    if isinstance(value, list):
        return [sanitize_raw(v) for v in value]
    return value


def sensitive_key(value: Any) -> bool:
    if not isinstance(value, str):
        return True
    canonical = re.sub(r"[^a-z0-9]", "", value.lower())
    return any(token in canonical for token in SENSITIVE_KEY_TOKENS)


def json_array(iteminfo: dict[str, Any], key: str) -> list[Any]:
    value = iteminfo.get(key)
    return value if isinstance(value, list) else []


def parse_price(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    numbers = [int(part.replace(",", "")) for part in re.findall(r"\d[\d,]*", value)]
    return min(numbers) if numbers else None


def normalize(item: dict[str, Any]) -> dict[str, Any]:
    content_id = item.get("content_id")
    if not isinstance(content_id, str) or not content_id.strip():
        raise ValueError("ITEM_CONTENT_ID_INVALID")
    iteminfo = item.get("iteminfo") if isinstance(item.get("iteminfo"), dict) else {}
    prices = item.get("prices") if isinstance(item.get("prices"), dict) else {}
    review = item.get("review") if isinstance(item.get("review"), dict) else {}
    contributors = {
        role: json_array(iteminfo, role)
        for role in ("actress", "actor", "author", "maker", "manufacture")
        if json_array(iteminfo, role)
    }
    current_raw = prices.get("price") if isinstance(prices.get("price"), str) else None
    list_raw = prices.get("list_price") if isinstance(prices.get("list_price"), str) else None
    current = parse_price(current_raw)
    listed = parse_price(list_raw)
    discount = listed - current if listed is not None and current is not None and listed >= current else None
    rate = round(discount * 100 / listed, 2) if discount is not None and listed else None
    extension = {
        key: item[key] for key in ("category_name", "floor_code", "floor_name", "number", "service_code", "service_name", "tachiyomi", "volume")
        if key in item
    }
    return {
        "content_id": content_id.strip(), "product_id": item.get("product_id"),
        "title": item.get("title"), "release_date_raw": item.get("date"),
        "item_url": item.get("URL"), "image": item.get("imageURL"),
        "contributors": contributors, "series": json_array(iteminfo, "series"),
        "genre": json_array(iteminfo, "genre"), "extension": extension,
        "current_price_raw": current_raw, "current_price_min": current,
        "list_price_raw": list_raw, "list_price_min": listed,
        "discount_amount": discount, "discount_rate": rate,
        "review_average": review.get("average") if isinstance(review.get("average"), (int, float)) else None,
        "review_count": review.get("count") if isinstance(review.get("count"), int) else None,
        "delivery": prices.get("deliveries"),
        "sanitized_raw": sanitize_raw(copy.deepcopy(item)),
    }


def ensure_database(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def register_sources(connection: sqlite3.Connection, targets: list[dict[str, str]]) -> None:
    for target in targets:
        connection.execute(
            "INSERT INTO category_sources(content_type,site,service,floor,collection_mode) VALUES(?,?,?,?, 'COLLECTION_ONLY') "
            "ON CONFLICT(content_type) DO NOTHING",
            (target["content_type"], target["site"], target["service"], target["floor"]),
        )
        stored = connection.execute(
            "SELECT site,service,floor,collection_mode,publication_allowed FROM category_sources WHERE content_type=?",
            (target["content_type"],),
        ).fetchone()
        expected = (target["site"], target["service"], target["floor"], "COLLECTION_ONLY", 0)
        if stored != expected:
            raise ValueError("SOURCE_IDENTITY_MISMATCH")


def fetch(target: dict[str, str], hits: int, api_id: str, affiliate_id: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({"api_id": api_id, "affiliate_id": affiliate_id, **{k: target[k] for k in ("site", "service", "floor")}, "hits": hits, "offset": 1, "sort": "date", "output": "json"})
    request = urllib.request.Request(ENDPOINT + "?" + query, headers={"User-Agent": "DATA-LAB-category-collector/0.1"})
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status != 200:
            raise RuntimeError("API_HTTP_ERROR")
        payload = json.load(response)
    result = payload.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("items"), list):
        raise ValueError("API_RESULT_INVALID")
    return result


def collect_target(connection: sqlite3.Connection, target: dict[str, str], hits: int, api_id: str, affiliate_id: str) -> None:
    source = connection.execute("SELECT source_id FROM category_sources WHERE content_type=?", (target["content_type"],)).fetchone()
    if source is None:
        raise RuntimeError("SOURCE_REGISTRATION_FAILED")
    source_id = source[0]
    run_id, started = str(uuid.uuid4()), utc_now()
    connection.execute("INSERT INTO category_collection_runs(run_id,source_id,started_at,status,source_sort,requested_hits) VALUES(?,?,?,'running','date',?)", (run_id, source_id, started, hits))
    connection.commit()
    try:
        result = fetch(target, hits, api_id, affiliate_id)
        items = [normalize(item) for item in result["items"]]
        digest = hashlib.sha256(json.dumps(sanitize_raw(result), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        observed = utc_now()
        with connection:
            for position, item in enumerate(items, 1):
                connection.execute(
                    "INSERT INTO category_items(source_id,content_id,product_id,title,release_date_raw,item_url,image_json,contributors_json,series_json,genre_json,source_extension_json,first_observed_at,last_observed_at,normalizer_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(source_id,content_id) DO UPDATE SET product_id=excluded.product_id,title=excluded.title,release_date_raw=excluded.release_date_raw,item_url=excluded.item_url,image_json=excluded.image_json,contributors_json=excluded.contributors_json,series_json=excluded.series_json,genre_json=excluded.genre_json,source_extension_json=excluded.source_extension_json,last_observed_at=excluded.last_observed_at,normalizer_version=excluded.normalizer_version",
                    (source_id,item["content_id"],item["product_id"],item["title"],item["release_date_raw"],item["item_url"],json.dumps(item["image"],ensure_ascii=False),json.dumps(item["contributors"],ensure_ascii=False),json.dumps(item["series"],ensure_ascii=False),json.dumps(item["genre"],ensure_ascii=False),json.dumps(item["extension"],ensure_ascii=False),observed,observed,NORMALIZER_VERSION),
                )
                item_id = connection.execute("SELECT item_id FROM category_items WHERE source_id=? AND content_id=?", (source_id,item["content_id"])).fetchone()[0]
                connection.execute(
                    "INSERT INTO category_item_snapshots(item_id,run_id,observed_at,current_price_raw,current_price_min,list_price_raw,list_price_min,discount_amount,discount_rate,review_average,review_count,source_sort,source_position,delivery_json,sanitized_raw_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (item_id,run_id,observed,item["current_price_raw"],item["current_price_min"],item["list_price_raw"],item["list_price_min"],item["discount_amount"],item["discount_rate"],item["review_average"],item["review_count"],"date",position,json.dumps(item["delivery"],ensure_ascii=False),json.dumps(item["sanitized_raw"],ensure_ascii=False)),
                )
            total = result.get("total_count") if isinstance(result.get("total_count"), int) else None
            connection.execute("UPDATE category_collection_runs SET finished_at=?,status='success',fetched_items=?,total_count=?,response_sha256=? WHERE run_id=?", (utc_now(),len(items),total,digest,run_id))
        print(f"target={target['content_type']} status=success fetched={len(items)}")
    except Exception:
        with connection:
            connection.execute("UPDATE category_collection_runs SET finished_at=?,status='failed',error_code='COLLECTION_FAILED' WHERE run_id=?", (utc_now(),run_id))
        print(f"target={target['content_type']} status=failed code=COLLECTION_FAILED", file=sys.stderr)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Isolated collection-only multi-category collector")
    parser.add_argument("--hits", type=int, default=50)
    parser.add_argument("--database", type=Path, default=DATABASE_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.hits <= 100:
        print("Error: hits must be between 1 and 100", file=sys.stderr); return 2
    targets = load_config()
    if args.dry_run:
        print(json.dumps({"status":"READY","mode":"COLLECTION_ONLY","targets":len(targets),"api_calls":0,"database_writes":0,"publication_allowed":False}, sort_keys=True)); return 0
    api_id, affiliate_id = load_secret("DMM_API_ID"), load_secret("DMM_AFFILIATE_ID")
    if not api_id or not affiliate_id:
        print("Error: required credentials are not configured", file=sys.stderr); return 3
    args.database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(args.database)
    try:
        ensure_database(connection)
        with connection: register_sources(connection, targets)
        failures = 0
        for index, target in enumerate(targets):
            if index: time.sleep(1.1)
            try: collect_target(connection, target, args.hits, api_id, affiliate_id)
            except Exception: failures += 1
        return 1 if failures else 0
    finally: connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
