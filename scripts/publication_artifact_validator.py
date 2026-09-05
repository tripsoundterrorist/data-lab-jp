"""Pure, fail-closed validation of in-memory Public Data artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping
from urllib.parse import urlsplit

from publication_gate import (
    GATE_VERSION, PUBLIC_POLICY_VERSION, PUBLIC_SCHEMA_VERSION,
    evaluate_publication_gate,
)
from rights_decision_policy import POLICY_VERSION as RIGHTS_POLICY_VERSION


VALIDATOR_VERSION = "0.1"
PASS = "PASS"
FAIL_CLOSED = "FAIL_CLOSED"
PUBLIC_ID_PATTERN = re.compile(r"itm_[0-9a-f]{24}\Z")

REASON_ORDER = (
    "MALFORMED_INPUT", "MALFORMED_JSON", "MISSING_MANIFEST", "MISSING_INDEX",
    "UNKNOWN_SCHEMA_VERSION", "UNKNOWN_POLICY_VERSION", "VERSION_MISMATCH",
    "UNKNOWN_FIELD", "FORBIDDEN_FIELD", "SECRET_LIKE_VALUE", "PATH_LEAK",
    "INVALID_PUBLIC_ID", "DUPLICATE_PUBLIC_ID", "COUNT_MISMATCH",
    "MISSING_DETAIL", "ORPHAN_DETAIL", "SHARD_MISMATCH", "INVALID_URL",
    "INDEX_DIGEST_MISMATCH", "DETAIL_DIGEST_MISMATCH", "BUILDER_CONTRACT_FAILURE",
    "CONTRADICTORY_PUBLICATION_STATE", "INTERNAL_ERROR",
)
FORBIDDEN_KEYS = frozenset({
    "product_description", "description", "user_review_text", "review_text",
    "actress_api_face_image", "actress_image_url", "person_list_image",
    "sample_video", "sample_movie_url", "video_capture", "raw_api_response",
    "api_id", "affiliate_id", "affiliate_url", "affiliateurl", "query_context",
    "query_context_json", "content_id", "product_id", "internal_db_id", "db_id",
    "item_id", "collection_run_id", "source_position", "source_offset",
    "raw_request_url", "environment", "env", "filesystem_path", "sqlite_path",
})
DERIVED_SCHEMA_FIELDS = frozenset({
    "derived_ranking", "derived_analysis", "derived_price_comparison",
    "review_count", "review_average",
})
_SECRET_VALUE = re.compile(
    r"(?i)(?:api|affiliate)[_-]?id\s*[:=]|(?:password|secret|token)\s*[:=]|"
    r"bearer\s+[a-z0-9._~-]{6,}|\.env(?:\b|[\\/])"
)
_PATH_VALUE = re.compile(
    r"(?i)(?:(?<![a-z])[a-z]:[\\/]|^\\\\|^/(?!/)|/home/|/users/|file:/{1,3})"
)
CHECKS = (
    "MANIFEST_PRESENT", "INDEX_PRESENT", "VERSIONS_MATCH", "JSON_VALID",
    "BUILDER_SCHEMA_CONTRACT", "PUBLIC_IDS_VALID", "DETAIL_REFERENCES_MATCH",
    "COUNTS_MATCH", "NESTED_FORBIDDEN_SCAN", "SECRET_SCAN", "PATH_SCAN",
    "URL_SCAN", "INDEX_DIGEST", "DETAIL_DIGEST", "RIGHTS_GATE",
)


@dataclass(frozen=True)
class ArtifactValidationResult:
    validator_version: str
    artifact_validation: str
    publication_allowed: bool
    schema_version: str | None
    policy_version: str | None
    item_count: int | None
    shard_count: int
    checks_passed: tuple[str, ...]
    reason_codes: tuple[str, ...]
    blocked_fields: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "validator_version": self.validator_version,
            "artifact_validation": self.artifact_validation,
            "publication_allowed": self.publication_allowed,
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "item_count": self.item_count,
            "shard_count": self.shard_count,
            "checks_passed": list(self.checks_passed),
            "reason_codes": list(self.reason_codes),
            "blocked_fields": list(self.blocked_fields),
            "warnings": list(self.warnings),
        }


_BUILDER: Any = None


def _builder() -> Any:
    global _BUILDER
    if _BUILDER is None:
        path = Path(__file__).resolve().with_name("build-public-data.py")
        spec = importlib.util.spec_from_file_location("artifact_builder_contract", path)
        if spec is None or spec.loader is None:
            raise RuntimeError("builder contract unavailable")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _BUILDER = module
    return _BUILDER


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


_NORMALIZED_FORBIDDEN = frozenset(_normalize_key(value) for value in FORBIDDEN_KEYS)


def _scan(value: Any, blocked: set[str], reasons: set[str], warnings: set[str]) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                reasons.add("UNKNOWN_FIELD")
                continue
            if _normalize_key(key) in _NORMALIZED_FORBIDDEN:
                blocked.add(key)
                reasons.add("FORBIDDEN_FIELD")
            if key in DERIVED_SCHEMA_FIELDS:
                warnings.add("NOT_IMPLEMENTED_IN_SCHEMA")
            _scan(child, blocked, reasons, warnings)
    elif isinstance(value, list):
        for child in value:
            _scan(child, blocked, reasons, warnings)
    elif isinstance(value, str):
        if _SECRET_VALUE.search(value):
            reasons.add("SECRET_LIKE_VALUE")
        if _PATH_VALUE.search(value):
            reasons.add("PATH_LEAK")


def _safe_url(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, str) or not value or _PATH_VALUE.search(value):
        return False
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username:
        return False
    host = (parsed.hostname or "").casefold()
    return host not in {"localhost", "127.0.0.1", "::1"} and not host.endswith(".localhost")


def _urls(value: Any, reasons: set[str]) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in {"image_url", "item_url"} and not _safe_url(child):
                reasons.add("INVALID_URL")
            _urls(child, reasons)
    elif isinstance(value, list):
        for child in value:
            _urls(child, reasons)


def _json_documents(files: Mapping[str, bytes], reasons: set[str]) -> dict[str, Any]:
    documents: dict[str, Any] = {}
    for path, content in files.items():
        if not isinstance(path, str) or not isinstance(content, bytes):
            reasons.add("MALFORMED_INPUT")
            continue
        candidate = Path(path)
        if candidate.is_absolute() or ".." in candidate.parts or "\\" in path:
            reasons.add("PATH_LEAK")
            continue
        try:
            documents[path] = json.loads(content.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            reasons.add("MALFORMED_JSON")
    return documents


def _result(
    reasons: set[str], blocked: set[str], warnings: set[str], *,
    schema: str | None, policy: str | None, item_count: int | None,
    shard_count: int, publication_allowed: bool = False,
) -> ArtifactValidationResult:
    ordered = tuple(code for code in REASON_ORDER if code in reasons)
    return ArtifactValidationResult(
        VALIDATOR_VERSION, PASS if not ordered else FAIL_CLOSED,
        publication_allowed if not ordered else False, schema, policy, item_count,
        shard_count, CHECKS if not ordered else (), ordered, tuple(sorted(blocked)),
        tuple(sorted(warnings)),
    )


def validate_artifacts(files: Any) -> ArtifactValidationResult:
    reasons: set[str] = set()
    blocked: set[str] = set()
    warnings: set[str] = set()
    schema = policy = None
    item_count = None
    shard_count = 0
    try:
        if not isinstance(files, Mapping):
            return _result({"MALFORMED_INPUT"}, blocked, warnings, schema=None, policy=None, item_count=None, shard_count=0)
        if GATE_VERSION != "0.3" or RIGHTS_POLICY_VERSION != "0.1":
            reasons.add("VERSION_MISMATCH")
        documents = _json_documents(files, reasons)
        manifest = documents.get("manifest.json")
        index = documents.get("index.json")
        if manifest is None:
            reasons.add("MISSING_MANIFEST")
        if index is None:
            reasons.add("MISSING_INDEX")
        detail_paths = {path for path in documents if path.startswith("items/")}
        shard_count = len(detail_paths)
        for document in documents.values():
            _scan(document, blocked, reasons, warnings)
            _urls(document, reasons)
        if not isinstance(manifest, dict) or not isinstance(index, dict):
            return _result(reasons or {"MALFORMED_INPUT"}, blocked, warnings, schema=None, policy=None, item_count=None, shard_count=shard_count)
        schema = manifest.get("public_schema_version")
        policy = manifest.get("public_policy_version")
        item_count = manifest.get("item_count") if type(manifest.get("item_count")) is int else None
        if schema != PUBLIC_SCHEMA_VERSION:
            reasons.add("UNKNOWN_SCHEMA_VERSION")
        if policy != PUBLIC_POLICY_VERSION:
            reasons.add("UNKNOWN_POLICY_VERSION")
        versions = {document.get("public_schema_version") for document in documents.values() if isinstance(document, dict)}
        if versions != {PUBLIC_SCHEMA_VERSION}:
            reasons.add("VERSION_MISMATCH")
        builder = _builder()
        try:
            builder.validate_manifest(manifest, len(index.get("items", [])) if isinstance(index.get("items"), list) else -1)
            builder.validate_index_document(index, len(index.get("items", [])) if isinstance(index.get("items"), list) else -1)
            for path in detail_paths:
                builder.validate_detail_document(documents[path])
            for item in index.get("items", []):
                builder.validate_index_item(item)
            for path in detail_paths:
                builder.validate_detail_item(documents[path]["item"])
        except Exception:
            reasons.add("BUILDER_CONTRACT_FAILURE")
        items = index.get("items")
        if not isinstance(items, list):
            reasons.add("BUILDER_CONTRACT_FAILURE")
            items = []
        public_ids = [item.get("public_id") for item in items if isinstance(item, dict)]
        if any(not isinstance(value, str) or PUBLIC_ID_PATTERN.fullmatch(value) is None for value in public_ids) or len(public_ids) != len(items):
            reasons.add("INVALID_PUBLIC_ID")
        if len(public_ids) != len(set(public_ids)):
            reasons.add("DUPLICATE_PUBLIC_ID")
        expected = {f"items/{value[4:6]}/{value}.json" for value in public_ids if isinstance(value, str) and PUBLIC_ID_PATTERN.fullmatch(value)}
        if expected - detail_paths:
            reasons.add("MISSING_DETAIL")
        if detail_paths - expected:
            reasons.add("ORPHAN_DETAIL")
        for path in detail_paths & expected:
            detail_id = documents[path].get("item", {}).get("public_id") if isinstance(documents[path], dict) else None
            if detail_id != Path(path).stem:
                reasons.add("SHARD_MISMATCH")
        if item_count != len(items):
            reasons.add("COUNT_MISMATCH")
        if manifest.get("index_sha256") != hashlib.sha256(files.get("index.json", b"")).hexdigest():
            reasons.add("INDEX_DIGEST_MISMATCH")
        safe_files = dict(files)
        if manifest.get("detail_aggregate_sha256") != builder.aggregate_detail_digest(safe_files):
            reasons.add("DETAIL_DIGEST_MISMATCH")
        gate = evaluate_publication_gate(files)
        if gate.rights_gate != PASS or gate.data_policy_gate != PASS:
            reasons.add("BUILDER_CONTRACT_FAILURE")
        if manifest.get("publication_status") == "public" and not gate.overall_eligible:
            reasons.add("CONTRADICTORY_PUBLICATION_STATE")
        return _result(
            reasons, blocked, warnings, schema=schema if isinstance(schema, str) else None,
            policy=policy if isinstance(policy, str) else None, item_count=item_count,
            shard_count=shard_count,
            publication_allowed=not reasons and gate.overall_eligible,
        )
    except Exception:
        return _result({"INTERNAL_ERROR"}, set(), set(), schema=None, policy=None, item_count=None, shard_count=0)


__all__ = [
    "ArtifactValidationResult", "FAIL_CLOSED", "PASS", "VALIDATOR_VERSION",
    "validate_artifacts",
]
