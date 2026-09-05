"""Fail-closed, multi-gate publication assessment for Public Data v0.1."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from revenue_mvp_official_answer_matrix import (
    AnswerDecision, assess_answer_matrix,
)
from rights_decision_policy import (
    APPROVED, DIRECT_SUPPORT_CONFIRMATION, POLICY_VERSION as RIGHTS_POLICY_VERSION,
    decision_for, validate_policy as validate_rights_policy,
)

GATE_VERSION = "0.3"
PUBLIC_SCHEMA_VERSION = "0.1"
PUBLIC_POLICY_VERSION = "0.1"
LOCAL_VALIDATION_ONLY = "local_validation_only"
PASS = "PASS"
CLOSED = "CLOSED"
PENDING_OFFICIAL_CONFIRMATION = "PENDING_OFFICIAL_CONFIRMATION"
VALID_GATE_STATUSES = frozenset({PASS, CLOSED, PENDING_OFFICIAL_CONFIRMATION})
PUBLIC_ID_PATTERN = re.compile(r"itm_[0-9a-f]{24}")
REQUIRED_ITEM_FIELDS = frozenset({"public_id", "title", "current_price", "last_observed_at"})

# Explicit public-name to Rights Decision Matrix mapping; no implicit conversion.
PUBLIC_RIGHTS_FIELD_MAP = {
    "title": "title", "image_url": "product_main_image",
    "item_url": "product_page_url", "maker": "maker", "series": "series",
    "actress": "actress_name", "genre": "genre", "current_price": "price",
    "review_count": "review_count", "review_average": "review_average",
    "derived_price_comparison": "derived_price_comparison",
    "derived_ranking": "derived_ranking", "derived_analysis": "derived_analysis",
}
PROHIBITED_PUBLIC_FIELDS = frozenset({
    "product_description", "description", "user_review_text", "review_text",
    "actress_api_face_image", "actress_image_url", "person_list_image",
    "dmm_books_product_image", "sample_video", "sample_movie_url",
    "video_capture", "raw_api_response", "api_id", "affiliate_id",
    "affiliate_url", "query_context", "query_context_json", "internal_db_id",
    "internal_id", "db_id", "database_id", "item_id", "content_id",
    "product_id", "collection_run_id", "source_offset", "source_position",
    "filesystem_path", "sqlite_path", "credential", "credentials", "token",
    "access_token",
})
PENDING_FIELDS = (
    "lifecycle_status", "api_zero_result_meaning", "sale_ended", "unpublished",
    "deleted", "affiliate_ineligible", "affiliate_url_presence_meaning",
    "rank_sort_semantics", "review_sort_semantics",
)
REASON_ORDER = (
    "FORBIDDEN_FIELD_PRESENT", "SECRET_PATTERN_DETECTED",
    "RIGHTS_POLICY_VERSION_MISMATCH", "RIGHTS_POLICY_INVALID",
    "UNKNOWN_RIGHTS_FIELD", "RIGHTS_NOT_APPROVED",
    "UNSUPPORTED_SCHEMA_VERSION", "UNSUPPORTED_POLICY_VERSION",
    "REQUIRED_FIELD_MISSING", "INVALID_PUBLIC_ID", "INVALID_TIMESTAMP",
    "INVALID_PUBLIC_DOCUMENT", "LIFECYCLE_GATE_PENDING",
    "SEMANTICS_GATE_PENDING", "PUBLICATION_STATUS_NOT_PUBLIC",
    "DATA_POLICY_GATE_CLOSED", "OFFICIAL_ANSWER_REVIEW_REQUIRED",
    "OFFICIAL_ANSWER_APPROVAL_INVALID", "UNKNOWN_GATE_STATUS",
)
SECRET_PATTERNS = (
    re.compile(r"(?i)(?:api|affiliate)[_-]?id\s*="),
    re.compile(r"(?i)(?:access[_-]?token|credential|password|secret)\s*[:=]"),
    re.compile(r"(?i)bearer\s+[a-z0-9._~-]{6,}"),
    re.compile(r"(?i)\.env(?:\b|[\\/])"),
)


@dataclass(frozen=True)
class PublicationGateResult:
    gate_version: str
    overall_eligible: bool
    publication_status: str
    rights_gate: str
    lifecycle_gate: str
    semantics_gate: str
    publication_status_gate: str
    data_policy_gate: str
    reason_codes: tuple[str, ...]
    approved_rights_fields: tuple[str, ...]
    blocked_fields: tuple[str, ...]
    pending_fields: tuple[str, ...]

    @property
    def eligible(self) -> bool:  # Existing builder compatibility.
        return self.overall_eligible

    @property
    def status(self) -> str:
        return "eligible" if self.overall_eligible else "blocked"

    @property
    def reasons(self) -> tuple[str, ...]:
        return self.reason_codes

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_version": self.gate_version,
            "overall_eligible": self.overall_eligible,
            "publication_status": self.publication_status,
            "rights_gate": self.rights_gate,
            "lifecycle_gate": self.lifecycle_gate,
            "semantics_gate": self.semantics_gate,
            "publication_status_gate": self.publication_status_gate,
            "data_policy_gate": self.data_policy_gate,
            "reason_codes": list(self.reason_codes),
            "approved_rights_fields": list(self.approved_rights_fields),
            "blocked_fields": list(self.blocked_fields),
            "pending_fields": list(self.pending_fields),
        }


def normalized_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


NORMALIZED_PROHIBITED_FIELDS = frozenset(
    normalized_field_name(field) for field in PROHIBITED_PUBLIC_FIELDS
)


def parse_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized).tzinfo is not None
    except ValueError:
        return False


def _scan_fields(value: Any, blocked: set[str], reasons: set[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                reasons.add("INVALID_PUBLIC_DOCUMENT")
                continue
            if normalized_field_name(key) in NORMALIZED_PROHIBITED_FIELDS:
                blocked.add(key)
                reasons.add("FORBIDDEN_FIELD_PRESENT")
            _scan_fields(child, blocked, reasons)
    elif isinstance(value, list):
        for child in value:
            _scan_fields(child, blocked, reasons)


def _decode(files: Mapping[str, bytes], known_secrets: Sequence[bytes], reasons: set[str]) -> dict[str, Any]:
    documents: dict[str, Any] = {}
    for path, content in files.items():
        if not isinstance(path, str) or not isinstance(content, bytes):
            reasons.add("INVALID_PUBLIC_DOCUMENT")
            continue
        relative = Path(path)
        if relative.is_absolute() or ".." in relative.parts:
            reasons.add("INVALID_PUBLIC_DOCUMENT")
            continue
        try:
            text = content.decode("utf-8")
            documents[path] = json.loads(text)
        except (UnicodeError, json.JSONDecodeError):
            reasons.add("INVALID_PUBLIC_DOCUMENT")
            continue
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            reasons.add("SECRET_PATTERN_DETECTED")
        if any(secret and secret in content for secret in known_secrets):
            reasons.add("SECRET_PATTERN_DETECTED")
    return documents


def _validate_item(item: Any, reasons: set[str]) -> None:
    if not isinstance(item, dict):
        reasons.add("INVALID_PUBLIC_DOCUMENT")
        return
    if not REQUIRED_ITEM_FIELDS <= set(item):
        reasons.add("REQUIRED_FIELD_MISSING")
    public_id = item.get("public_id")
    if not isinstance(public_id, str) or PUBLIC_ID_PATTERN.fullmatch(public_id) is None:
        reasons.add("INVALID_PUBLIC_ID")
    if not isinstance(item.get("title"), str) or not item["title"].strip():
        reasons.add("REQUIRED_FIELD_MISSING")
    price = item.get("current_price")
    if not isinstance(price, int) or isinstance(price, bool) or price < 0:
        reasons.add("REQUIRED_FIELD_MISSING")
    if not parse_timestamp(item.get("last_observed_at")):
        reasons.add("INVALID_TIMESTAMP")


def _validate_documents(documents: Mapping[str, Any], reasons: set[str]) -> None:
    manifest, index = documents.get("manifest.json"), documents.get("index.json")
    if not isinstance(manifest, dict) or not isinstance(index, dict):
        reasons.add("INVALID_PUBLIC_DOCUMENT")
        return
    if manifest.get("public_schema_version") != PUBLIC_SCHEMA_VERSION:
        reasons.add("UNSUPPORTED_SCHEMA_VERSION")
    if manifest.get("public_policy_version") != PUBLIC_POLICY_VERSION:
        reasons.add("UNSUPPORTED_POLICY_VERSION")
    if index.get("public_schema_version") != PUBLIC_SCHEMA_VERSION:
        reasons.add("UNSUPPORTED_SCHEMA_VERSION")
    for document in (manifest, index):
        for field in ("generated_at", "as_of"):
            if not parse_timestamp(document.get(field)):
                reasons.add("INVALID_TIMESTAMP")
    items = index.get("items")
    if not isinstance(items, list):
        reasons.add("INVALID_PUBLIC_DOCUMENT")
        items = []
    if type(manifest.get("item_count")) is not int or manifest["item_count"] != len(items):
        reasons.add("INVALID_PUBLIC_DOCUMENT")
    identifiers: list[str] = []
    for item in items:
        _validate_item(item, reasons)
        if isinstance(item, dict) and isinstance(item.get("public_id"), str):
            identifiers.append(item["public_id"])
    if len(identifiers) != len(set(identifiers)):
        reasons.add("INVALID_PUBLIC_DOCUMENT")
    expected = {f"items/{value[4:6]}/{value}.json" for value in identifiers if PUBLIC_ID_PATTERN.fullmatch(value)}
    actual = {path for path in documents if path.startswith("items/")}
    if expected != actual:
        reasons.add("INVALID_PUBLIC_DOCUMENT")
    for path in actual:
        detail = documents[path]
        if not isinstance(detail, dict):
            reasons.add("INVALID_PUBLIC_DOCUMENT")
            continue
        if detail.get("public_schema_version") != PUBLIC_SCHEMA_VERSION:
            reasons.add("UNSUPPORTED_SCHEMA_VERSION")
        for field in ("generated_at", "as_of"):
            if not parse_timestamp(detail.get(field)):
                reasons.add("INVALID_TIMESTAMP")
        item = detail.get("item")
        _validate_item(item, reasons)
        if not isinstance(item, dict) or item.get("public_id") != Path(path).stem or item.get("public_id") not in identifiers:
            reasons.add("INVALID_PUBLIC_DOCUMENT")


def overall_from_gates(*statuses: str) -> bool:
    """True only when every required gate has a known PASS status."""
    if not statuses or any(status not in VALID_GATE_STATUSES for status in statuses):
        return False
    return all(status == PASS for status in statuses)


def _ordered(reasons: set[str]) -> tuple[str, ...]:
    return tuple(code for code in REASON_ORDER if code in reasons)


def _failed_result(reasons: set[str]) -> PublicationGateResult:
    reasons.add("INVALID_PUBLIC_DOCUMENT")
    return PublicationGateResult(
        GATE_VERSION, False, "unknown", CLOSED, PENDING_OFFICIAL_CONFIRMATION,
        PENDING_OFFICIAL_CONFIRMATION, CLOSED, CLOSED, _ordered(reasons), (), (),
        PENDING_FIELDS,
    )


def evaluate(
    files: Mapping[str, bytes],
    known_secrets: Sequence[bytes],
    *, rights_policy_version: str,
    official_answer_entries: Mapping[str, AnswerDecision] | None,
    explicit_official_answer_review_approval: bool,
) -> PublicationGateResult:
    reasons: set[str] = set()
    blocked: set[str] = set()
    documents = _decode(files, known_secrets, reasons)
    for document in documents.values():
        _scan_fields(document, blocked, reasons)
    _validate_documents(documents, reasons)
    manifest = documents.get("manifest.json")
    publication_status = manifest.get("publication_status") if isinstance(manifest, dict) else "unknown"
    rights_fields = manifest.get("rights_review_required") if isinstance(manifest, dict) else None
    approved: list[str] = []
    if rights_policy_version != RIGHTS_POLICY_VERSION:
        reasons.add("RIGHTS_POLICY_VERSION_MISMATCH")
    if validate_rights_policy():
        reasons.add("RIGHTS_POLICY_INVALID")
    if not isinstance(rights_fields, list) or any(not isinstance(field, str) for field in rights_fields):
        reasons.add("INVALID_PUBLIC_DOCUMENT")
        rights_fields = []
    for public_field in rights_fields:
        policy_field = PUBLIC_RIGHTS_FIELD_MAP.get(public_field)
        if policy_field is None:
            reasons.add("UNKNOWN_RIGHTS_FIELD")
            blocked.add(public_field)
            continue
        try:
            decision = decision_for(policy_field)
        except KeyError:
            reasons.add("UNKNOWN_RIGHTS_FIELD")
            blocked.add(public_field)
            continue
        if decision.public_display != APPROVED or decision.evidence_type != DIRECT_SUPPORT_CONFIRMATION:
            reasons.add("RIGHTS_NOT_APPROVED")
            blocked.add(public_field)
        else:
            approved.append(public_field)
    rights_blockers = {
        "FORBIDDEN_FIELD_PRESENT", "SECRET_PATTERN_DETECTED",
        "RIGHTS_POLICY_VERSION_MISMATCH", "RIGHTS_POLICY_INVALID",
        "UNKNOWN_RIGHTS_FIELD", "RIGHTS_NOT_APPROVED", "INVALID_PUBLIC_DOCUMENT",
    }
    rights_gate = PASS if not (reasons & rights_blockers) else CLOSED
    official_answers = (
        assess_answer_matrix(official_answer_entries)
        if official_answer_entries is not None else None
    )
    if type(explicit_official_answer_review_approval) is not bool:
        reasons.add("OFFICIAL_ANSWER_APPROVAL_INVALID")
    official_reviewed = (
        official_answers is not None
        and official_answers.core_publication_candidate is True
        and explicit_official_answer_review_approval is True
    )
    lifecycle_gate = PASS if official_reviewed else PENDING_OFFICIAL_CONFIRMATION
    semantics_gate = PASS if official_reviewed else PENDING_OFFICIAL_CONFIRMATION
    publication_status_gate = PASS if publication_status == "public" else CLOSED
    data_reasons = {
        "UNSUPPORTED_SCHEMA_VERSION", "UNSUPPORTED_POLICY_VERSION",
        "REQUIRED_FIELD_MISSING", "INVALID_PUBLIC_ID", "INVALID_TIMESTAMP",
        "INVALID_PUBLIC_DOCUMENT", "FORBIDDEN_FIELD_PRESENT", "SECRET_PATTERN_DETECTED",
    }
    data_policy_gate = PASS if not (reasons & data_reasons) else CLOSED
    if not official_reviewed:
        reasons.update({
            "LIFECYCLE_GATE_PENDING", "SEMANTICS_GATE_PENDING",
            "OFFICIAL_ANSWER_REVIEW_REQUIRED",
        })
    if publication_status_gate != PASS:
        reasons.add("PUBLICATION_STATUS_NOT_PUBLIC")
    if data_policy_gate != PASS:
        reasons.add("DATA_POLICY_GATE_CLOSED")
    statuses = (rights_gate, lifecycle_gate, semantics_gate, publication_status_gate, data_policy_gate)
    if any(status not in VALID_GATE_STATUSES for status in statuses):
        reasons.add("UNKNOWN_GATE_STATUS")
    return PublicationGateResult(
        GATE_VERSION, overall_from_gates(*statuses), publication_status if isinstance(publication_status, str) else "unknown",
        rights_gate, lifecycle_gate, semantics_gate, publication_status_gate,
        data_policy_gate, _ordered(reasons), tuple(dict.fromkeys(approved)),
        tuple(sorted(blocked)), () if official_reviewed else PENDING_FIELDS,
    )


def evaluate_publication_gate(
    files: Mapping[str, bytes],
    known_secrets: Sequence[bytes] = (),
    *,
    rights_policy_version: str = RIGHTS_POLICY_VERSION,
    official_answer_entries: Mapping[str, AnswerDecision] | None = None,
    explicit_official_answer_review_approval: bool = False,
) -> PublicationGateResult:
    try:
        return evaluate(
            files, known_secrets, rights_policy_version=rights_policy_version,
            official_answer_entries=official_answer_entries,
            explicit_official_answer_review_approval=explicit_official_answer_review_approval,
        )
    except Exception:
        return _failed_result(set())


__all__ = [
    "CLOSED", "GATE_VERSION", "LOCAL_VALIDATION_ONLY", "PASS",
    "PENDING_OFFICIAL_CONFIRMATION", "PUBLIC_POLICY_VERSION",
    "PUBLIC_RIGHTS_FIELD_MAP", "PUBLIC_SCHEMA_VERSION", "PublicationGateResult",
    "evaluate_publication_gate", "overall_from_gates",
]
