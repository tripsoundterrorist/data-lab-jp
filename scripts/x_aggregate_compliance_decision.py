"""Validate four independent X aggregate COMPLIANCE decisions.

The validator records review evidence only.  It never authorizes posting,
external sending, profile changes, or publication.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from typing import Any


VERSION = "0.1"
RECORDED = "X_AGGREGATE_COMPLIANCE_DECISIONS_RECORDED"
BLOCKED = "X_AGGREGATE_COMPLIANCE_DECISION_BLOCKED"
DECISION = "RECORD_X_AGGREGATE_COMPLIANCE_DECISIONS"
FINDING_KEYS = frozenset({
    "TEXT_AGGREGATE_ALLOWED",
    "BRAND_CHART_ALLOWED",
    "PROFILE_WEBSITE_FIELD_ALLOWED",
    "POST_LINK_ALLOWED",
})
RECEIPT_FIELDS = frozenset({
    "version",
    "decision",
    "decided_at",
    "packet_sha256",
    "reviewer_role",
    "findings",
})
FINDING_FIELDS = frozenset({"status", "source_url", "reviewed_at"})


@dataclass(frozen=True)
class DecisionResult:
    version: str
    status: str
    packet_sha256: str | None
    findings: dict[str, str]
    posting_allowed: bool
    external_send_allowed: bool
    profile_change_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["reason_codes"] = list(self.reason_codes)
        return result


def _result(
    status: str,
    digest: str | None,
    findings: dict[str, str] | None,
    reasons: tuple[str, ...],
) -> DecisionResult:
    return DecisionResult(
        VERSION,
        status,
        digest,
        findings or {},
        False,
        False,
        False,
        reasons,
    )


def _aware_datetime(value: Any) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return False
    return parsed.tzinfo is not None


def validate(packet_bytes: Any, receipt: Any) -> DecisionResult:
    if type(packet_bytes) is not bytes:
        return _result(BLOCKED, None, None, ("PACKET_BYTES_INVALID",))
    digest = hashlib.sha256(packet_bytes).hexdigest()
    try:
        packet = json.loads(packet_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return _result(BLOCKED, digest, None, ("PACKET_JSON_INVALID",))

    if type(receipt) is not dict or set(receipt) != RECEIPT_FIELDS:
        return _result(BLOCKED, digest, None, ("RECEIPT_SCHEMA_INVALID",))
    if receipt.get("version") != VERSION:
        return _result(BLOCKED, digest, None, ("RECEIPT_VERSION_INVALID",))
    if receipt.get("decision") != DECISION:
        return _result(BLOCKED, digest, None, ("DECISION_NOT_RECORDED",))
    if receipt.get("packet_sha256") != digest:
        return _result(BLOCKED, digest, None, ("PACKET_HASH_MISMATCH",))
    if receipt.get("reviewer_role") != "03_COMPLIANCE":
        return _result(BLOCKED, digest, None, ("REVIEWER_ROLE_INVALID",))
    if not _aware_datetime(receipt.get("decided_at")):
        return _result(BLOCKED, digest, None, ("DECIDED_AT_INVALID",))

    findings = receipt.get("findings")
    if type(findings) is not dict or set(findings) != FINDING_KEYS:
        return _result(BLOCKED, digest, None, ("FINDINGS_SCHEMA_INVALID",))

    normalized: dict[str, str] = {}
    for key in sorted(FINDING_KEYS):
        finding = findings.get(key)
        if type(finding) is not dict or set(finding) != FINDING_FIELDS:
            return _result(BLOCKED, digest, None, (f"{key}_SCHEMA_INVALID",))
        status = finding.get("status")
        if status not in {"ALLOWED", "BLOCKED"}:
            return _result(BLOCKED, digest, None, (f"{key}_STATUS_INVALID",))
        source_url = finding.get("source_url")
        if type(source_url) is not str or not source_url.startswith("https://"):
            return _result(BLOCKED, digest, None, (f"{key}_SOURCE_INVALID",))
        if not _aware_datetime(finding.get("reviewed_at")):
            return _result(BLOCKED, digest, None, (f"{key}_REVIEWED_AT_INVALID",))
        normalized[key] = status

    packet_ready = (
        type(packet) is dict
        and packet.get("status") == "READY_FOR_COMPLIANCE_REVIEW"
        and packet.get("manual_post_candidate") is False
        and packet.get("posting_performed") is False
        and packet.get("compliance_review_required") is True
        and packet.get("distribution_allowed") is False
        and packet.get("external_post_authorized") is False
        and type(packet.get("candidates")) is list
        and len(packet["candidates"]) == 3
    )
    if not packet_ready:
        return _result(BLOCKED, digest, normalized, ("PACKET_NOT_READY_FOR_REVIEW",))

    return _result(RECORDED, digest, normalized, ())


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
        result = _result(BLOCKED, None, None, ("DECISION_INPUT_UNAVAILABLE",))
    else:
        result = validate(packet_bytes, receipt)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == RECORDED else 2


if __name__ == "__main__":
    raise SystemExit(main())
