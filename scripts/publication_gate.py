from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence


ALLOWED_SCHEMA_VERSIONS = frozenset({"0.1"})
ALLOWED_POLICY_VERSIONS = frozenset({"0.1"})
PUBLIC_ID_PATTERN = re.compile(r"itm_[0-9a-f]{24}")
REQUIRED_ITEM_FIELDS = frozenset(
    {"public_id", "title", "current_price", "last_observed_at"}
)

REASON_ORDER = (
    "PUBLICATION_STATUS_NOT_PUBLIC",
    "RIGHTS_REVIEW_PENDING",
    "UNSUPPORTED_SCHEMA_VERSION",
    "UNSUPPORTED_POLICY_VERSION",
    "REQUIRED_FIELD_MISSING",
    "FORBIDDEN_FIELD_PRESENT",
    "SECRET_PATTERN_DETECTED",
    "INVALID_PUBLIC_ID",
    "INVALID_TIMESTAMP",
    "INVALID_PUBLIC_DOCUMENT",
)

FORBIDDEN_FIELDS = frozenset(
    {
        "internal_db_id",
        "internal_id",
        "db_id",
        "database_id",
        "item_id",
        "content_id",
        "product_id",
        "api_id",
        "affiliate_id",
        "affiliate_url",
        "raw_api_response",
        "query_context_json",
        "collection_run_id",
        "source_offset",
        "source_position",
        "filesystem_path",
        "sqlite_path",
        "credential",
        "credentials",
        "token",
        "access_token",
        "description",
        "review_text",
        "sample_movie_url",
        "actress_image_url",
    }
)

SECRET_PATTERNS = (
    re.compile(r"(?i)(?:api|affiliate)[_-]?id\s*="),
    re.compile(r"(?i)(?:access[_-]?token|credential|password|secret)\s*[:=]"),
    re.compile(r"(?i)bearer\s+[a-z0-9._~-]{6,}"),
    re.compile(r"(?i)\.env(?:\b|[\\/])"),
)


@dataclass(frozen=True)
class PublicationGateResult:
    eligible: bool
    status: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "status": self.status,
            "reasons": list(self.reasons),
        }


def normalized_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


NORMALIZED_FORBIDDEN_FIELDS = frozenset(
    normalized_field_name(field_name) for field_name in FORBIDDEN_FIELDS
)


def add_reason(reasons: set[str], code: str) -> None:
    if code not in REASON_ORDER:
        raise ValueError("unknown publication gate reason")
    reasons.add(code)


def parse_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def scan_forbidden_fields(value: Any, reasons: set[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                add_reason(reasons, "INVALID_PUBLIC_DOCUMENT")
                continue
            if normalized_field_name(key) in NORMALIZED_FORBIDDEN_FIELDS:
                add_reason(reasons, "FORBIDDEN_FIELD_PRESENT")
            scan_forbidden_fields(child, reasons)
    elif isinstance(value, list):
        for child in value:
            scan_forbidden_fields(child, reasons)


def validate_item(item: Any, reasons: set[str]) -> None:
    if not isinstance(item, dict):
        add_reason(reasons, "INVALID_PUBLIC_DOCUMENT")
        return
    if not REQUIRED_ITEM_FIELDS <= set(item):
        add_reason(reasons, "REQUIRED_FIELD_MISSING")
    public_id = item.get("public_id")
    if not isinstance(public_id, str) or PUBLIC_ID_PATTERN.fullmatch(public_id) is None:
        add_reason(reasons, "INVALID_PUBLIC_ID")
    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        add_reason(reasons, "REQUIRED_FIELD_MISSING")
    price = item.get("current_price")
    if not isinstance(price, int) or isinstance(price, bool) or price < 0:
        add_reason(reasons, "REQUIRED_FIELD_MISSING")
    if not parse_timestamp(item.get("last_observed_at")):
        add_reason(reasons, "INVALID_TIMESTAMP")


def decoded_documents(
    files: Mapping[str, bytes], reasons: set[str], known_secrets: Sequence[bytes]
) -> dict[str, Any]:
    documents: dict[str, Any] = {}
    for path, content in files.items():
        if not isinstance(path, str) or not isinstance(content, bytes):
            add_reason(reasons, "INVALID_PUBLIC_DOCUMENT")
            continue
        relative = Path(path)
        if relative.is_absolute() or ".." in relative.parts:
            add_reason(reasons, "INVALID_PUBLIC_DOCUMENT")
            continue
        try:
            text = content.decode("utf-8")
            documents[path] = json.loads(text)
        except (UnicodeError, json.JSONDecodeError):
            add_reason(reasons, "INVALID_PUBLIC_DOCUMENT")
            continue
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            add_reason(reasons, "SECRET_PATTERN_DETECTED")
        if any(secret and secret in content for secret in known_secrets):
            add_reason(reasons, "SECRET_PATTERN_DETECTED")
    return documents


def evaluate(
    files: Mapping[str, bytes], known_secrets: Sequence[bytes]
) -> PublicationGateResult:
    reasons: set[str] = set()
    documents = decoded_documents(files, reasons, known_secrets)
    manifest = documents.get("manifest.json")
    index = documents.get("index.json")
    if not isinstance(manifest, dict) or not isinstance(index, dict):
        add_reason(reasons, "INVALID_PUBLIC_DOCUMENT")
        return result_from_reasons(reasons)

    if manifest.get("publication_status") != "public":
        add_reason(reasons, "PUBLICATION_STATUS_NOT_PUBLIC")
    pending = manifest.get("rights_review_required")
    if not isinstance(pending, list) or pending:
        add_reason(reasons, "RIGHTS_REVIEW_PENDING")
    if manifest.get("public_schema_version") not in ALLOWED_SCHEMA_VERSIONS:
        add_reason(reasons, "UNSUPPORTED_SCHEMA_VERSION")
    if manifest.get("public_policy_version") not in ALLOWED_POLICY_VERSIONS:
        add_reason(reasons, "UNSUPPORTED_POLICY_VERSION")

    for field in ("generated_at", "as_of"):
        if not parse_timestamp(manifest.get(field)):
            add_reason(reasons, "INVALID_TIMESTAMP")
    if index.get("public_schema_version") not in ALLOWED_SCHEMA_VERSIONS:
        add_reason(reasons, "UNSUPPORTED_SCHEMA_VERSION")
    for field in ("generated_at", "as_of"):
        if not parse_timestamp(index.get(field)):
            add_reason(reasons, "INVALID_TIMESTAMP")

    items = index.get("items")
    if not isinstance(items, list):
        add_reason(reasons, "INVALID_PUBLIC_DOCUMENT")
        items = []
    declared_count = manifest.get("item_count")
    if (
        not isinstance(declared_count, int)
        or isinstance(declared_count, bool)
        or declared_count != len(items)
    ):
        add_reason(reasons, "INVALID_PUBLIC_DOCUMENT")

    identifiers: list[str] = []
    for item in items:
        validate_item(item, reasons)
        if isinstance(item, dict) and isinstance(item.get("public_id"), str):
            identifiers.append(item["public_id"])
    if len(identifiers) != len(set(identifiers)):
        add_reason(reasons, "INVALID_PUBLIC_DOCUMENT")

    expected_details = {
        f"items/{identifier[4:6]}/{identifier}.json"
        for identifier in identifiers
        if PUBLIC_ID_PATTERN.fullmatch(identifier)
    }
    actual_details = {path for path in documents if path.startswith("items/")}
    if expected_details != actual_details:
        add_reason(reasons, "INVALID_PUBLIC_DOCUMENT")
    for path in actual_details:
        document = documents[path]
        if not isinstance(document, dict):
            add_reason(reasons, "INVALID_PUBLIC_DOCUMENT")
            continue
        if document.get("public_schema_version") not in ALLOWED_SCHEMA_VERSIONS:
            add_reason(reasons, "UNSUPPORTED_SCHEMA_VERSION")
        for field in ("generated_at", "as_of"):
            if not parse_timestamp(document.get(field)):
                add_reason(reasons, "INVALID_TIMESTAMP")
        detail_item = document.get("item")
        validate_item(detail_item, reasons)
        if (
            not isinstance(detail_item, dict)
            or detail_item.get("public_id") != Path(path).stem
            or detail_item.get("public_id") not in identifiers
        ):
            add_reason(reasons, "INVALID_PUBLIC_DOCUMENT")

    for document in documents.values():
        scan_forbidden_fields(document, reasons)
    return result_from_reasons(reasons)


def result_from_reasons(reasons: set[str]) -> PublicationGateResult:
    ordered = tuple(code for code in REASON_ORDER if code in reasons)
    return PublicationGateResult(
        eligible=not ordered,
        status="eligible" if not ordered else "blocked",
        reasons=ordered,
    )


def evaluate_publication_gate(
    files: Mapping[str, bytes], known_secrets: Sequence[bytes] = ()
) -> PublicationGateResult:
    try:
        return evaluate(files, known_secrets)
    except Exception:
        return result_from_reasons({"INVALID_PUBLIC_DOCUMENT"})
