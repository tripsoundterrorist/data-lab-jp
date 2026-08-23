from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from publication_gate import evaluate_publication_gate


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = ROOT / "data" / "data-lab.db"
DEFAULT_OUTPUT_PATH = Path(tempfile.gettempdir()) / "data-lab-public-data-v0.1"
PUBLIC_SCHEMA_VERSION = "0.1"
PUBLIC_POLICY_VERSION = "0.1"
PUBLIC_ID_NAMESPACE = "data-lab-public-item-v0.1"
PUBLIC_ENTITY_NAMESPACE = "data-lab-public-entity-v0.1"

# Public-field policy is the single source of truth for every emitted object.
# Validators consume these exact sets, so adding a field to a builder without
# explicitly updating this policy fails closed. Text values remain JSON text;
# a future UI must render them as text (for example with textContent), not HTML.
PUBLIC_ALLOWED_FIELDS = {
    "manifest": frozenset(
        {
            "public_schema_version",
            "public_policy_version",
            "generated_at",
            "as_of",
            "item_count",
            "data_confidence_version",
            "price_analysis_version",
            "publication_status",
            "rights_review_required",
            "price_analysis_scope",
            "price_analysis_caveats",
            "index_path",
            "item_detail_pattern",
            "index_sha256",
            "detail_aggregate_sha256",
        }
    ),
    "index_document": frozenset(
        {"public_schema_version", "generated_at", "as_of", "items"}
    ),
    "detail_document": frozenset(
        {"public_schema_version", "generated_at", "as_of", "item"}
    ),
    "index_item": frozenset(
        {
            "public_id",
            "title",
            "image_url",
            "current_price",
            "data_confidence",
            "price_analysis",
            "last_observed_at",
        }
    ),
    "detail_item": frozenset(
        {
            "public_id",
            "title",
            "image_url",
            "item_url",
            "metadata",
            "current_price",
            "price_observed_at",
            "last_observed_at",
            "data_confidence",
            "price_analysis",
        }
    ),
    "metadata": frozenset({"maker", "series", "actress", "genre"}),
    "metadata_entity": frozenset({"public_id", "name"}),
    "confidence_summary": frozenset({"score", "label", "version"}),
    "confidence_detail": frozenset(
        {"score", "label", "version", "components", "warnings"}
    ),
    "confidence_label": frozenset({"code", "en", "ja"}),
    "confidence_components": frozenset(
        {
            "freshness",
            "observation_depth",
            "metadata_completeness",
            "price_data",
            "temporal_confidence",
        }
    ),
    "price_summary": frozenset(
        {"version", "observed_set_percentile", "percentile_method", "price_band"}
    ),
    "price_detail": frozenset(
        {
            "version",
            "observed_set_percentile",
            "percentile_method",
            "price_band",
            "genre_comparisons",
            "maker_comparison",
            "price_history",
            "warnings",
        }
    ),
    "price_band": frozenset({"code", "en", "ja"}),
    "comparison": frozenset(
        {
            "public_group_id",
            "status",
            "sample_size",
            "minimum_sample_size",
            "median",
            "percentile",
            "percentile_method",
        }
    ),
    "maker_comparison": frozenset({"available", "comparisons"}),
    "price_history": frozenset(
        {
            "first_observed_price",
            "first_price_observed_at",
            "latest_observed_price",
            "latest_price_observed_at",
            "min_observed_price",
            "max_observed_price",
            "price_observation_count",
            "distinct_price_observation_dates",
            "price_observation_span_days",
        }
    ),
}

RIGHTS_REVIEW_REQUIRED = (
    "title",
    "image_url",
    "item_url",
    "maker",
    "series",
    "actress",
    "genre",
)

PUBLIC_FORBIDDEN_FIELDS = frozenset(
    {
        "api_id",
        "affiliate_id",
        "affiliate_url",
        "affiliateURL",
        "raw_api_response",
        "query_context_json",
        "collection_run_id",
        "source_offset",
        "source_position",
        "item_id",
        "content_id",
        "product_id",
        "filesystem_path",
        "sqlite_path",
        "traceback",
        "debug",
        "description",
        "review_text",
        "sample_movie_url",
        "actress_image_url",
    }
)

FORBIDDEN_TEXT_PATTERNS = {
    "API_ID_PARAMETER": re.compile(r"api_id\s*=", re.IGNORECASE),
    "AFFILIATE_ID_PARAMETER": re.compile(r"affiliate_id\s*=", re.IGNORECASE),
    "AFFILIATE_URL_FIELD": re.compile(r"affiliateurl", re.IGNORECASE),
    "ENV_REFERENCE": re.compile(r"\.env(?:\b|[\\/])", re.IGNORECASE),
    "QUERY_CONTEXT": re.compile(r"query_context_json", re.IGNORECASE),
    "REPOSITORY_PATH": re.compile(r"[a-z]:[\\/]github[\\/]", re.IGNORECASE),
    "SQLITE_PATH": re.compile(r"(?:[a-z]:[\\/][^\"\r\n]*\.(?:db|sqlite3?))", re.IGNORECASE),
    "TRACEBACK": re.compile(r"traceback", re.IGNORECASE),
}

INDEX_ITEM_KEYS = PUBLIC_ALLOWED_FIELDS["index_item"]
DETAIL_ITEM_KEYS = PUBLIC_ALLOWED_FIELDS["detail_item"]


class PublicDataError(Exception):
    pass


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print("public data build failed: INVALID_ARGUMENT", file=sys.stderr)
        raise SystemExit(2)


def load_analysis_module(name: str, filename: str) -> ModuleType:
    path = ROOT / "scripts" / filename
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise PublicDataError("ANALYSIS_MODULE_LOAD_FAILED")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def parse_timestamp(value: str, argument_name: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{argument_name} must be an ISO8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{argument_name} must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def timestamp_argument(name: str):
    def parser(value: str) -> datetime:
        try:
            return parse_timestamp(value, name)
        except ValueError as error:
            raise argparse.ArgumentTypeError(str(error)) from error

    return parser


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def read_only_connection(path: Path) -> sqlite3.Connection:
    resolved = path.resolve()
    if not resolved.is_file():
        raise PublicDataError("DATABASE_NOT_FOUND")
    connection = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def public_item_id(site: str, service: str, floor: str, content_id: str) -> str:
    source = "\0".join((PUBLIC_ID_NAMESPACE, site, service, floor, content_id))
    return "itm_" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:24]


def public_entity_id(entity_type: str, internal_id: str) -> str:
    source = "\0".join((PUBLIC_ENTITY_NAMESPACE, entity_type, internal_id))
    return entity_type[:3] + "_" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def parse_public_entities(value: Any, entity_type: str) -> tuple[list[dict[str, str]], dict[str, str]]:
    if value is None:
        return [], {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise PublicDataError("INVALID_MASTER_METADATA_JSON") from error
    if not isinstance(parsed, list):
        raise PublicDataError("INVALID_MASTER_METADATA_JSON")
    public: list[dict[str, str]] = []
    identifier_map: dict[str, str] = {}
    seen: set[str] = set()
    for entity in parsed:
        if not isinstance(entity, dict):
            continue
        internal_id = entity.get("id")
        name = entity.get("name")
        if internal_id is None or not isinstance(name, str) or not name:
            continue
        internal_key = str(internal_id)
        public_id = public_entity_id(entity_type, internal_key)
        identifier_map[internal_key] = public_id
        if public_id not in seen:
            public.append({"public_id": public_id, "name": name})
            seen.add(public_id)
    public.sort(key=lambda entity: entity["public_id"])
    return public, identifier_map


# Image policy: image_url is sourced only from image_url_large. This builder
# never stores, transforms, or generates image binaries, and exposes no person
# or actress image field. Affiliate routing is a future UI/routing-layer concern;
# affiliate URLs and identifiers must never enter these analysis JSON files.
MASTER_SQL = """
SELECT id, site, service, floor, content_id, title,
       maker_json, series_json, actress_json, genre_json,
       image_url_large, item_url
FROM items
ORDER BY id
"""


def read_master_items(database_path: Path) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    with closing(read_only_connection(database_path)) as connection:
        for row in connection.execute(MASTER_SQL):
            metadata: dict[str, list[dict[str, str]]] = {}
            entity_maps: dict[str, dict[str, str]] = {}
            for key, entity_type in (
                ("maker", "maker"),
                ("series", "series"),
                ("actress", "actress"),
                ("genre", "genre"),
            ):
                entities, identifier_map = parse_public_entities(
                    row[f"{key}_json"], entity_type
                )
                metadata[key] = entities
                entity_maps[key] = identifier_map
            result[row["id"]] = {
                "public_id": public_item_id(
                    row["site"], row["service"], row["floor"], row["content_id"]
                ),
                "title": row["title"],
                "image_url": row["image_url_large"],
                "item_url": row["item_url"],
                "metadata": metadata,
                "entity_maps": entity_maps,
            }
    return result


def transform_label(label: dict[str, Any]) -> dict[str, str]:
    return {"code": label["code"], "en": label["en"], "ja": label["ja"]}


def public_confidence(item: dict[str, Any], detailed: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "score": item["score"],
        "label": transform_label(item["label"]),
        "version": item["score_version"],
    }
    if detailed:
        result["components"] = item["components"]
        result["warnings"] = item["warnings"]
    return result


def transform_comparison(
    comparison: dict[str, Any], entity_type: str, identifier_map: dict[str, str]
) -> dict[str, Any]:
    internal_id = str(comparison["id"])
    public_id = identifier_map.get(internal_id)
    if public_id is None:
        public_id = public_entity_id(entity_type, internal_id)
    result = {
        "public_group_id": public_id,
        "status": comparison["status"],
        "sample_size": comparison["sample_size"],
        "minimum_sample_size": comparison["minimum_sample_size"],
        "median": comparison["median"],
        "percentile": comparison["percentile"],
        "percentile_method": comparison.get("percentile_method"),
    }
    return result


def public_price_analysis(
    item: dict[str, Any], master: dict[str, Any], detailed: bool
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "version": "0.1",
        "observed_set_percentile": item["percentile"],
        "percentile_method": item["percentile_method"],
        "price_band": item["price_band"],
    }
    if detailed:
        result["genre_comparisons"] = [
            transform_comparison(
                comparison, "genre", master["entity_maps"]["genre"]
            )
            for comparison in item["genre_comparisons"]
        ]
        result["maker_comparison"] = {
            "available": item["maker_comparison"]["available"],
            "comparisons": [
                transform_comparison(
                    comparison, "maker", master["entity_maps"]["maker"]
                )
                for comparison in item["maker_comparison"]["comparisons"]
            ],
        }
        result["price_history"] = item["price_history_stats"]
        result["warnings"] = item["warnings"]
    return result


def validate_url(value: Any, field_name: str, nullable: bool) -> None:
    if value is None and nullable:
        return
    if not isinstance(value, str) or not value:
        raise PublicDataError(f"INVALID_{field_name.upper()}")
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username:
        raise PublicDataError(f"INVALID_{field_name.upper()}")
    query_names = {name.lower() for name, _ in parse_qsl(parsed.query)}
    if {"api_id", "affiliate_id"} & query_names:
        raise PublicDataError(f"FORBIDDEN_{field_name.upper()}_QUERY")


def require_exact_keys(value: dict[str, Any], expected: set[str], code: str) -> None:
    if set(value) != expected:
        raise PublicDataError(code)


def validate_score(value: Any, code: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise PublicDataError(code)
    if not 0 <= value <= 100:
        raise PublicDataError(code)


def validate_comparison(value: dict[str, Any]) -> None:
    require_exact_keys(
        value,
        PUBLIC_ALLOWED_FIELDS["comparison"],
        "INVALID_PUBLIC_COMPARISON_KEYS",
    )
    if not isinstance(value["public_group_id"], str) or re.fullmatch(
        r"(?:gen|mak)_[0-9a-f]{16}", value["public_group_id"]
    ) is None:
        raise PublicDataError("INVALID_PUBLIC_GROUP_ID")
    if not isinstance(value["sample_size"], int) or value["sample_size"] < 0:
        raise PublicDataError("INVALID_PUBLIC_SAMPLE_SIZE")
    if not isinstance(value["minimum_sample_size"], int) or value[
        "minimum_sample_size"
    ] < 0:
        raise PublicDataError("INVALID_PUBLIC_MINIMUM_SAMPLE_SIZE")
    if value["percentile"] is not None:
        validate_score(value["percentile"], "INVALID_PUBLIC_PERCENTILE")


def validate_common_item_fields(item: dict[str, Any]) -> None:
    if not isinstance(item["public_id"], str) or re.fullmatch(
        r"itm_[0-9a-f]{24}", item["public_id"]
    ) is None:
        raise PublicDataError("INVALID_PUBLIC_ID")
    if not isinstance(item["title"], str):
        raise PublicDataError("INVALID_PUBLIC_TITLE")
    validate_url(item["image_url"], "image_url", nullable=True)
    if item["current_price"] is not None and (
        not isinstance(item["current_price"], int) or item["current_price"] < 0
    ):
        raise PublicDataError("INVALID_PUBLIC_CURRENT_PRICE")
    validate_score(item["data_confidence"]["score"], "INVALID_PUBLIC_SCORE")
    require_exact_keys(
        item["data_confidence"]["label"],
        PUBLIC_ALLOWED_FIELDS["confidence_label"],
        "INVALID_PUBLIC_CONFIDENCE_LABEL_KEYS",
    )
    if item["price_analysis"]["price_band"] is not None:
        require_exact_keys(
            item["price_analysis"]["price_band"],
            PUBLIC_ALLOWED_FIELDS["price_band"],
            "INVALID_PUBLIC_PRICE_BAND_KEYS",
        )
    percentile_value = item["price_analysis"]["observed_set_percentile"]
    if percentile_value is not None:
        validate_score(percentile_value, "INVALID_PUBLIC_PERCENTILE")


def validate_index_item(item: dict[str, Any]) -> None:
    require_exact_keys(item, INDEX_ITEM_KEYS, "INVALID_PUBLIC_INDEX_ITEM_KEYS")
    validate_common_item_fields(item)
    require_exact_keys(
        item["data_confidence"],
        PUBLIC_ALLOWED_FIELDS["confidence_summary"],
        "INVALID_PUBLIC_CONFIDENCE_SUMMARY_KEYS",
    )
    require_exact_keys(
        item["price_analysis"],
        PUBLIC_ALLOWED_FIELDS["price_summary"],
        "INVALID_PUBLIC_PRICE_SUMMARY_KEYS",
    )


def validate_detail_item(item: dict[str, Any]) -> None:
    require_exact_keys(item, DETAIL_ITEM_KEYS, "INVALID_PUBLIC_DETAIL_ITEM_KEYS")
    validate_common_item_fields(item)
    validate_url(item["item_url"], "item_url", nullable=True)
    if item["data_confidence"]["version"] != "0.1":
        raise PublicDataError("INVALID_CONFIDENCE_VERSION")
    if item["price_analysis"]["version"] != "0.1":
        raise PublicDataError("INVALID_PRICE_ANALYSIS_VERSION")
    require_exact_keys(
        item["data_confidence"],
        PUBLIC_ALLOWED_FIELDS["confidence_detail"],
        "INVALID_PUBLIC_CONFIDENCE_DETAIL_KEYS",
    )
    require_exact_keys(
        item["price_analysis"],
        PUBLIC_ALLOWED_FIELDS["price_detail"],
        "INVALID_PUBLIC_PRICE_DETAIL_KEYS",
    )
    components = item["data_confidence"]["components"]
    require_exact_keys(
        components,
        PUBLIC_ALLOWED_FIELDS["confidence_components"],
        "INVALID_PUBLIC_CONFIDENCE_COMPONENTS",
    )
    for score in components.values():
        validate_score(score, "INVALID_PUBLIC_COMPONENT_SCORE")
    for comparison in item["price_analysis"]["genre_comparisons"]:
        validate_comparison(comparison)
    for comparison in item["price_analysis"]["maker_comparison"]["comparisons"]:
        validate_comparison(comparison)
    require_exact_keys(
        item["price_analysis"]["maker_comparison"],
        PUBLIC_ALLOWED_FIELDS["maker_comparison"],
        "INVALID_PUBLIC_MAKER_COMPARISON_KEYS",
    )
    require_exact_keys(
        item["price_analysis"]["price_history"],
        PUBLIC_ALLOWED_FIELDS["price_history"],
        "INVALID_PUBLIC_PRICE_HISTORY_KEYS",
    )
    require_exact_keys(
        item["metadata"],
        PUBLIC_ALLOWED_FIELDS["metadata"],
        "INVALID_PUBLIC_METADATA_KEYS",
    )
    for entities in item["metadata"].values():
        for entity in entities:
            require_exact_keys(
                entity,
                PUBLIC_ALLOWED_FIELDS["metadata_entity"],
                "INVALID_PUBLIC_METADATA_ENTITY_KEYS",
            )
            if re.fullmatch(
                r"(?:mak|ser|act|gen)_[0-9a-f]{16}", entity["public_id"]
            ) is None:
                raise PublicDataError("INVALID_PUBLIC_METADATA_GROUP_ID")


def validate_manifest(manifest: dict[str, Any], expected_item_count: int) -> None:
    require_exact_keys(
        manifest,
        PUBLIC_ALLOWED_FIELDS["manifest"],
        "INVALID_PUBLIC_MANIFEST_KEYS",
    )
    if manifest["public_schema_version"] != PUBLIC_SCHEMA_VERSION:
        raise PublicDataError("INVALID_PUBLIC_SCHEMA_VERSION")
    if manifest["public_policy_version"] != PUBLIC_POLICY_VERSION:
        raise PublicDataError("INVALID_PUBLIC_POLICY_VERSION")
    if manifest["data_confidence_version"] != "0.1":
        raise PublicDataError("INVALID_CONFIDENCE_VERSION")
    if manifest["price_analysis_version"] != "0.1":
        raise PublicDataError("INVALID_PRICE_ANALYSIS_VERSION")
    if manifest["item_count"] != expected_item_count:
        raise PublicDataError("INVALID_PUBLIC_ITEM_COUNT")
    if manifest["publication_status"] != "local_validation_only":
        raise PublicDataError("INVALID_PUBLICATION_STATUS")
    if tuple(manifest["rights_review_required"]) != RIGHTS_REVIEW_REQUIRED:
        raise PublicDataError("INVALID_RIGHTS_REVIEW_POLICY")


def validate_index_document(document: dict[str, Any], expected_item_count: int) -> None:
    require_exact_keys(
        document,
        PUBLIC_ALLOWED_FIELDS["index_document"],
        "INVALID_PUBLIC_INDEX_DOCUMENT_KEYS",
    )
    if document["public_schema_version"] != PUBLIC_SCHEMA_VERSION:
        raise PublicDataError("INVALID_PUBLIC_SCHEMA_VERSION")
    if len(document["items"]) != expected_item_count:
        raise PublicDataError("INVALID_PUBLIC_ITEM_COUNT")


def validate_detail_document(document: dict[str, Any]) -> None:
    require_exact_keys(
        document,
        PUBLIC_ALLOWED_FIELDS["detail_document"],
        "INVALID_PUBLIC_DETAIL_DOCUMENT_KEYS",
    )
    if document["public_schema_version"] != PUBLIC_SCHEMA_VERSION:
        raise PublicDataError("INVALID_PUBLIC_SCHEMA_VERSION")


def json_bytes(value: Any) -> bytes:
    text = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (text + "\n").encode("utf-8")


def load_secret_values() -> list[str]:
    values: list[str] = []
    env_file = ROOT / ".env"
    if env_file.is_file():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                _, value = stripped.split("=", 1)
                candidate = value.strip().strip("\"'")
                if len(candidate) >= 6:
                    values.append(candidate)
        except OSError as error:
            raise PublicDataError("SECRET_SCAN_SOURCE_READ_FAILED") from error
    for name, value in os.environ.items():
        upper_name = name.upper()
        if any(token in upper_name for token in ("API_ID", "AFFILIATE_ID")):
            if len(value) >= 6:
                values.append(value)
    return sorted(set(values))


def normalized_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


NORMALIZED_FORBIDDEN_FIELDS = frozenset(
    normalized_field_name(field_name) for field_name in PUBLIC_FORBIDDEN_FIELDS
)


def scan_field_names(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise PublicDataError("PUBLIC_FIELD_NAME_NOT_STRING")
            if normalized_field_name(key) in NORMALIZED_FORBIDDEN_FIELDS:
                raise PublicDataError("PUBLIC_FORBIDDEN_FIELD_NAME")
            scan_field_names(child)
    elif isinstance(value, list):
        for child in value:
            scan_field_names(child)


def safety_scan(files: dict[str, bytes]) -> None:
    secrets = load_secret_values()
    for relative_path, content in files.items():
        text = content.decode("utf-8")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as error:
            raise PublicDataError("PUBLIC_JSON_PARSE_FAILURE") from error
        scan_field_names(parsed)
        for code, pattern in FORBIDDEN_TEXT_PATTERNS.items():
            if pattern.search(text):
                raise PublicDataError(f"PUBLIC_SAFETY_SCAN_{code}")
        if any(secret in text for secret in secrets):
            raise PublicDataError("PUBLIC_SAFETY_SCAN_SECRET_VALUE")
        if ".." in Path(relative_path).parts:
            raise PublicDataError("INVALID_PUBLIC_OUTPUT_PATH")


def detail_relative_path(public_id: str) -> str:
    shard = public_id[4:6]
    return f"items/{shard}/{public_id}.json"


def aggregate_detail_digest(files: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for path in sorted(key for key in files if key.startswith("items/")):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(files[path])
    return digest.hexdigest()


def build_documents(
    database_path: Path,
    as_of: datetime,
    generated_at: datetime,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    confidence_module = load_analysis_module(
        "data_lab_confidence", "calculate-data-confidence.py"
    )
    price_module = load_analysis_module("data_lab_price", "calculate-price-analysis.py")
    confidence_result = confidence_module.calculate(database_path, as_of)
    price_result = price_module.calculate(database_path, as_of)
    master_items = read_master_items(database_path)

    confidence_by_id = {item["item_id"]: item for item in confidence_result["items"]}
    price_by_id = {item["item_id"]: item for item in price_result["items"]}
    if set(master_items) != set(confidence_by_id) or set(master_items) != set(price_by_id):
        raise PublicDataError("ANALYSIS_ITEM_SET_MISMATCH")

    public_ids = [item["public_id"] for item in master_items.values()]
    if len(public_ids) != len(set(public_ids)):
        raise PublicDataError("DUPLICATE_PUBLIC_ID")

    index_items: list[dict[str, Any]] = []
    detail_items: list[dict[str, Any]] = []
    for internal_id in sorted(master_items):
        master = master_items[internal_id]
        confidence = confidence_by_id[internal_id]
        price = price_by_id[internal_id]
        last_observed_at = confidence["observation_stats"]["last_observed_at"]
        index_item = {
            "public_id": master["public_id"],
            "title": master["title"] or "",
            "image_url": master["image_url"],
            "current_price": price["current_price"],
            "data_confidence": public_confidence(confidence, detailed=False),
            "price_analysis": public_price_analysis(price, master, detailed=False),
            "last_observed_at": last_observed_at,
        }
        detail_item = {
            "public_id": master["public_id"],
            "title": master["title"] or "",
            "image_url": master["image_url"],
            "item_url": master["item_url"],
            "metadata": master["metadata"],
            "current_price": price["current_price"],
            "price_observed_at": price["current_price_observed_at"],
            "last_observed_at": last_observed_at,
            "data_confidence": public_confidence(confidence, detailed=True),
            "price_analysis": public_price_analysis(price, master, detailed=True),
        }
        validate_index_item(index_item)
        validate_detail_item(detail_item)
        index_items.append(index_item)
        detail_items.append(detail_item)

    index_items.sort(key=lambda item: item["public_id"])
    detail_items.sort(key=lambda item: item["public_id"])
    index_document = {
        "public_schema_version": PUBLIC_SCHEMA_VERSION,
        "generated_at": iso_utc(generated_at),
        "as_of": iso_utc(as_of),
        "items": index_items,
    }
    validate_index_document(index_document, len(index_items))
    files = {"index.json": json_bytes(index_document)}
    for item in detail_items:
        detail_document = {
            "public_schema_version": PUBLIC_SCHEMA_VERSION,
            "generated_at": iso_utc(generated_at),
            "as_of": iso_utc(as_of),
            "item": item,
        }
        validate_detail_document(detail_document)
        files[detail_relative_path(item["public_id"])] = json_bytes(detail_document)

    detail_digest = aggregate_detail_digest(files)
    manifest = {
        "public_schema_version": PUBLIC_SCHEMA_VERSION,
        "public_policy_version": PUBLIC_POLICY_VERSION,
        "generated_at": iso_utc(generated_at),
        "as_of": iso_utc(as_of),
        "item_count": len(index_items),
        "data_confidence_version": confidence_result["score_version"],
        "price_analysis_version": price_result["version"],
        "publication_status": "local_validation_only",
        "rights_review_required": list(RIGHTS_REVIEW_REQUIRED),
        "price_analysis_scope": "current_data_lab_observed_set",
        "price_analysis_caveats": [
            "OBSERVED_SET_IS_PARTIAL_AND_DATE_SORT_BIASED",
            "NOT_MARKET_PRICE_OR_VALUE_SCORE",
            "SHORT_OBSERVATION_WINDOW",
        ],
        "index_path": "index.json",
        "item_detail_pattern": "items/{shard}/{public_id}.json",
        "index_sha256": hashlib.sha256(files["index.json"]).hexdigest(),
        "detail_aggregate_sha256": detail_digest,
    }
    validate_manifest(manifest, len(index_items))
    files["manifest.json"] = json_bytes(manifest)
    safety_scan(files)

    detail_sizes = [
        len(content) for path, content in files.items() if path.startswith("items/")
    ]
    summary = {
        "public_schema_version": PUBLIC_SCHEMA_VERSION,
        "public_policy_version": PUBLIC_POLICY_VERSION,
        "as_of": iso_utc(as_of),
        "generated_at": iso_utc(generated_at),
        "item_count": len(index_items),
        "validated_item_count": len(detail_items),
        "duplicate_public_id_count": 0,
        "missing_detail_count": 0,
        "orphan_detail_count": 0,
        "secret_scan": "passed",
        "url_validation": "passed",
        "confidence_match": "passed",
        "price_analysis_match": "passed",
        "sizes": {
            "manifest_bytes": len(files["manifest.json"]),
            "index_bytes": len(files["index.json"]),
            "detail_total_bytes": sum(detail_sizes),
            "detail_average_bytes": round(sum(detail_sizes) / len(detail_sizes), 2),
            "detail_max_bytes": max(detail_sizes),
            "total_bytes": sum(len(content) for content in files.values()),
        },
        "digests": {
            "manifest_sha256": hashlib.sha256(files["manifest.json"]).hexdigest(),
            "index_sha256": hashlib.sha256(files["index.json"]).hexdigest(),
            "detail_aggregate_sha256": detail_digest,
        },
    }
    return files, summary


def ensure_safe_output_path(output_path: Path) -> Path:
    resolved = output_path.resolve()
    repository = ROOT.resolve()
    if resolved == repository or repository in resolved.parents:
        raise PublicDataError("OUTPUT_INSIDE_REPOSITORY_FORBIDDEN")
    if resolved.parent == resolved:
        raise PublicDataError("INVALID_OUTPUT_PATH")
    return resolved


def atomic_write(output_path: Path, files: dict[str, bytes]) -> None:
    target = ensure_safe_output_path(output_path)
    if target.exists() and not target.is_dir():
        raise PublicDataError("OUTPUT_TARGET_IS_NOT_DIRECTORY")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f"{target.name}.tmp-", dir=str(target.parent))
    )
    backup: Path | None = None
    try:
        for relative_path, content in files.items():
            destination = temporary / Path(relative_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        if target.exists():
            backup = target.with_name(f"{target.name}.previous-{uuid.uuid4().hex}")
            os.replace(target, backup)
        os.replace(temporary, target)
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
        if backup is not None and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise


def print_summary(summary: dict[str, Any], dry_run: bool, output: Path) -> None:
    print("PUBLIC DATA MODEL v0.1")
    print(f"Mode: {'dry-run' if dry_run else 'generated'}")
    print(f"As of: {summary['as_of']}")
    print(f"Generated at: {summary['generated_at']}")
    print(f"Items: {summary['item_count']}")
    print(f"Validated: {summary['validated_item_count']}")
    print(f"Secret scan: {summary['secret_scan']}")
    print(f"URL validation: {summary['url_validation']}")
    print(
        "Publication eligible: "
        f"{'yes' if summary['publication_gate']['eligible'] else 'no'}"
    )
    print(f"Total bytes: {summary['sizes']['total_bytes']}")
    if not dry_run:
        print(f"Output: {output.resolve()}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = SafeArgumentParser(
        description="Build allowlisted, static public DATA LAB JSON locally."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--as-of", type=timestamp_argument("--as-of"))
    parser.add_argument("--generated-at", type=timestamp_argument("--generated-at"))
    parser.add_argument(
        "--publication-mode",
        choices=("local-validation", "production"),
        default="local-validation",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def error_result(code: str) -> dict[str, str]:
    return {
        "public_schema_version": PUBLIC_SCHEMA_VERSION,
        "error": code,
    }


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    now = datetime.now(timezone.utc)
    as_of = args.as_of or now
    generated_at = args.generated_at or now
    try:
        files, summary = build_documents(args.db, as_of, generated_at)
        gate = evaluate_publication_gate(
            files,
            tuple(value.encode("utf-8") for value in load_secret_values()),
        )
        summary["publication_gate"] = gate.to_dict()
        if args.publication_mode == "production" and not gate.eligible:
            raise PublicDataError("PUBLICATION_GATE_BLOCKED")
        if not args.dry_run:
            atomic_write(args.output, files)
    except PublicDataError as error:
        if args.json:
            print(json.dumps(error_result(str(error)), ensure_ascii=False))
        else:
            print(f"public data build failed: {error}", file=sys.stderr)
        return 2
    except (OSError, sqlite3.Error):
        if args.json:
            print(json.dumps(error_result("LOCAL_IO_OR_DATABASE_ERROR"), ensure_ascii=False))
        else:
            print("public data build failed: LOCAL_IO_OR_DATABASE_ERROR", file=sys.stderr)
        return 2
    except Exception:
        if args.json:
            print(json.dumps(error_result("UNEXPECTED_ERROR"), ensure_ascii=False))
        else:
            print("public data build failed: UNEXPECTED_ERROR", file=sys.stderr)
        return 3

    summary["mode"] = "dry-run" if args.dry_run else "generated"
    summary["output_written"] = not args.dry_run
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    else:
        print_summary(summary, args.dry_run, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
