"""Synthetic-only field disposition contract after the preconnection syntax gate.

This records a narrow candidate projection for the existing strict parser. It
does not accept real transport output or claim compatibility with live schemas.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import affiliate_cta_approved_context as approved
import affiliate_cta_network_disabled_wire_adapter as adapter
import affiliate_cta_offline_provider_factory as factory
import affiliate_cta_transport_capability_manifest as capability


PROJECTION_CONTROL_VERSION = "offline-wire-projection-redaction-v0.1"
KEEP = "KEEP"
DROP_SENSITIVE = "DROP_SENSITIVE"
REJECT_UNKNOWN = "REJECT_UNKNOWN"
UNCONFIRMED = "UNCONFIRMED"
CONFIRMED = "CONFIRMED"
PROJECT_CONTROL = "PROJECT_CONTROL"
ACCEPTED = "SYNTHETIC_PROJECTION_ACCEPTED"
BLOCKED = "SYNTHETIC_PROJECTION_BLOCKED"
FAIL_CLOSED = "SYNTHETIC_PROJECTION_FAIL_CLOSED"

_OFFICIAL_DIGEST = "72e3486589983e13389e8f3abd94c51ed7379bc89c9043e93cca17d14313ff19"
_CONTROL_DIGEST = "0e274278c73379fbabc64be9f6a50c41a8e5eea6f087a41640dbe2d29d31a43f"
_CHECKED_AT = "2026-09-23"
_ROOT_KEYS = frozenset({"result"})
_RESULT_KEYS = frozenset({"status", "result_count", "total_count", "first_position", "items"})
_ITEM_KEYS = frozenset({"content_id", "affiliateURL"})


@dataclass(frozen=True, repr=False)
class FieldDisposition:
    field_path: str
    disposition: str
    classification: str
    source_reference: str
    source_digest: str
    source_checked_at: str
    scope: str
    reason: str
    superseded: bool = False

    def __repr__(self) -> str:
        return "<FieldDisposition>"


@dataclass(frozen=True, repr=False)
class ProjectionReceipt:
    status: str
    reason_code: str
    kept_field_count: int
    adapter_validated: bool
    owner_consumed: bool
    request_echo_dropped: bool = False
    connection_allowed: bool = False
    activation_allowed: bool = False
    publication_allowed: bool = False
    compatibility_verified: bool = False

    def __repr__(self) -> str:
        return "<ProjectionReceipt>"


def fixed_field_dispositions_for_test() -> tuple[FieldDisposition, ...]:
    keep = tuple(FieldDisposition(
        path, KEEP, CONFIRMED, "official-wire-contract-review", _OFFICIAL_DIGEST,
        _CHECKED_AT, "strict-synthetic-minimum", "existing-strict-parser-subset",
    ) for path in (
        "result", "result.status", "result.result_count", "result.total_count",
        "result.first_position", "result.items", "result.items[0].content_id",
        "result.items[0].affiliateURL",
    ))
    return keep + (
        FieldDisposition("request", DROP_SENSITIVE, PROJECT_CONTROL,
                         "preconnection-live-evidence-q1-q5-review", _CONTROL_DIGEST,
                         _CHECKED_AT, "synthetic-projection-design",
                         "request-echo-is-never-retained-or-exported"),
        FieldDisposition("*.unknown", REJECT_UNKNOWN, PROJECT_CONTROL,
                         "preconnection-live-evidence-q1-q5-review", _CONTROL_DIGEST,
                         _CHECKED_AT, "synthetic-projection-design",
                         "unknown-fields-are-not-silently-stripped"),
        FieldDisposition("*.additional", UNCONFIRMED, PROJECT_CONTROL,
                         "preconnection-live-evidence-q1-q5-review", _CONTROL_DIGEST,
                         _CHECKED_AT, "synthetic-projection-design",
                         "additional-field-schema-is-unconfirmed"),
    )


def production_projection() -> None:
    return None


def _receipt(status: str, reason: str, *, kept: int = 0, adapter_ok: bool = False,
             owner_ok: bool = False, echo: bool = False) -> ProjectionReceipt:
    return ProjectionReceipt(status, reason, kept, adapter_ok, owner_ok, echo)


def _dispositions_valid(value: Any) -> bool:
    if type(value) is not tuple or len(value) != 11:
        return False
    expected = {item.field_path: item for item in fixed_field_dispositions_for_test()}
    seen: set[str] = set()
    for item in value:
        if type(item) is not FieldDisposition:
            return False
        fields = (item.field_path, item.disposition, item.classification, item.source_reference,
                  item.source_digest, item.source_checked_at, item.scope, item.reason)
        if any(type(field) is not str for field in fields) or type(item.superseded) is not bool:
            return False
        if item.superseded is not False or item.field_path in seen:
            return False
        seen.add(item.field_path)
        expected_item = expected.get(item.field_path)
        if expected_item is None or item != expected_item:
            return False
    return seen == set(expected)


def _exact_keys(value: Any, expected: frozenset[str]) -> bool:
    return type(value) is dict and len(value) == len(expected) and all(
        type(key) is str and key in expected for key in value
    )


def _project_minimum_subset(payload: Any) -> tuple[dict[str, Any] | None, str, bool]:
    """Copy only documented KEEP fields. This performs no product semantics."""
    if type(payload) is not dict:
        return None, "PAYLOAD_TYPE_BLOCKED", False
    # Inspecting only exact built-in keys is safe; request's value is never read.
    if "request" in payload:
        return None, "REQUEST_ECHO_DROPPED", True
    if not _exact_keys(payload, _ROOT_KEYS):
        return None, "ROOT_FIELD_BLOCKED", False
    result = payload["result"]
    if not _exact_keys(result, _RESULT_KEYS):
        return None, "RESULT_FIELD_BLOCKED", False
    items = result["items"]
    if type(items) is not list or len(items) != 1:
        return None, "ITEM_CARDINALITY_BLOCKED", False
    item = items[0]
    if not _exact_keys(item, _ITEM_KEYS):
        return None, "ITEM_FIELD_BLOCKED", False
    # A new exact dict/list shape limits the handoff to the declared KEEP set.
    projected = {"result": {
        "status": result["status"], "result_count": result["result_count"],
        "total_count": result["total_count"], "first_position": result["first_position"],
        "items": [{"content_id": item["content_id"], "affiliateURL": item["affiliateURL"]}],
    }}
    return projected, "KEEP_SUBSET", False


def _run_offline_projection_for_test(*, dispositions: Any, payload: Any,
                                     requested_content_id: Any, provider: Any,
                                     public_id: Any) -> ProjectionReceipt:
    """Post-syntax synthetic projection, then one adapter and owner handoff."""
    try:
        if not _dispositions_valid(dispositions):
            return _receipt(BLOCKED, "DISPOSITION_EVIDENCE_BLOCKED")
        if not factory._synthetic_owner_ready_for_test(provider, public_id):
            return _receipt(BLOCKED, "OWNER_BLOCKED")
        projected, reason, echo = _project_minimum_subset(payload)
        if projected is None:
            return _receipt(BLOCKED, reason, echo=echo)
        observation = adapter.validate_synthetic_fixture_for_offline_harness(projected, requested_content_id)
        if type(observation) is not adapter.ValidatedSyntheticFixtureObservation:
            return _receipt(BLOCKED, "SEMANTIC_VALIDATION_BLOCKED", kept=8)
        consumed = factory._consume_validated_synthetic_for_test(provider, public_id, observation)
        if type(consumed) is not approved._InternalObservation:
            return _receipt(FAIL_CLOSED, "OWNER_CONSUMPTION_BLOCKED", kept=8, adapter_ok=True)
        return _receipt(ACCEPTED, "SYNTHETIC_ONLY", kept=8, adapter_ok=True, owner_ok=True)
    except Exception:
        return _receipt(FAIL_CLOSED, "INTERNAL_FAILURE")


OFFICIAL_WIRE_CONTRACT_VERSION = capability.OFFICIAL_WIRE_CONTRACT_VERSION

__all__ = [
    "ACCEPTED", "BLOCKED", "DROP_SENSITIVE", "FAIL_CLOSED", "FieldDisposition",
    "KEEP", "OFFICIAL_WIRE_CONTRACT_VERSION", "ProjectionReceipt", "PROJECT_CONTROL",
    "PROJECTION_CONTROL_VERSION", "REJECT_UNKNOWN", "UNCONFIRMED", "fixed_field_dispositions_for_test",
    "production_projection",
]
