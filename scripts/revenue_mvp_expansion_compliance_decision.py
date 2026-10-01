"""Validate an explicit manual COMPLIANCE decision against an immutable packet."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from typing import Any


VERSION = "0.1"
CONFIRMED = "EXPANSION_COMPLIANCE_CONFIRMED"
BLOCKED = "EXPANSION_COMPLIANCE_DECISION_BLOCKED"
DECISION = "CONFIRM_EXPANSION_COMPLIANCE"
RECEIPT_FIELDS = frozenset({
    "version", "decision", "decided_at", "packet_sha256", "reviewer_role",
})


@dataclass(frozen=True)
class ComplianceDecision:
    version: str
    status: str
    packet_sha256: str | None
    compliance_publication_confirmed: bool
    publication_allowed: bool
    production_write_allowed: bool
    deployment_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(status: str, digest: str | None, reasons: tuple[str, ...]) -> ComplianceDecision:
    return ComplianceDecision(
        VERSION, status, digest, status == CONFIRMED,
        False, False, False, reasons,
    )


def validate(packet_bytes: Any, receipt: Any) -> ComplianceDecision:
    if type(packet_bytes) is not bytes:
        return _result(BLOCKED, None, ("PACKET_BYTES_INVALID",))
    digest = hashlib.sha256(packet_bytes).hexdigest()
    try:
        packet = json.loads(packet_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return _result(BLOCKED, digest, ("PACKET_JSON_INVALID",))
    if type(receipt) is not dict or set(receipt) != RECEIPT_FIELDS:
        return _result(BLOCKED, digest, ("RECEIPT_SCHEMA_INVALID",))
    if receipt.get("version") != VERSION:
        return _result(BLOCKED, digest, ("RECEIPT_VERSION_INVALID",))
    if receipt.get("decision") != DECISION:
        return _result(BLOCKED, digest, ("DECISION_NOT_CONFIRMED",))
    if receipt.get("packet_sha256") != digest:
        return _result(BLOCKED, digest, ("PACKET_HASH_MISMATCH",))
    if receipt.get("reviewer_role") != "DATA_LAB_OWNER":
        return _result(BLOCKED, digest, ("REVIEWER_ROLE_INVALID",))
    try:
        decided_at = datetime.fromisoformat(
            receipt["decided_at"].replace("Z", "+00:00")
        )
        if decided_at.tzinfo is None:
            raise ValueError
    except (AttributeError, TypeError, ValueError):
        return _result(BLOCKED, digest, ("DECIDED_AT_INVALID",))

    packet_ready = (
        type(packet) is dict
        and packet.get("version") == "0.1"
        and packet.get("status") == "READY_FOR_MANUAL_COMPLIANCE_DECISION"
        and packet.get("target_item_count") == 300
        and packet.get("official_lifecycle_core_confirmed") is True
        and packet.get("candidate_lookup_ready_count") == 300
        and packet.get("candidate_redirect_ready_count") == 300
        and packet.get("candidate_runtime_ready_count") == 300
        and packet.get("presentation_policy_verified") is True
        and packet.get("product_funnel_window_closed") is True
        and packet.get("product_funnel_review_completed") is True
        and packet.get("compliance_publication_confirmed") is False
        and packet.get("publication_allowed") is False
        and packet.get("production_write_allowed") is False
        and packet.get("reason_codes") == []
    )
    if not packet_ready:
        return _result(BLOCKED, digest, ("PACKET_NOT_READY_FOR_DECISION",))
    return _result(CONFIRMED, digest, ())


def main() -> int:
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        packet_bytes = args.packet.read_bytes()
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        result = _result(BLOCKED, None, ("DECISION_INPUT_UNAVAILABLE",))
    else:
        result = validate(packet_bytes, receipt)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == CONFIRMED else 2


if __name__ == "__main__":
    raise SystemExit(main())
