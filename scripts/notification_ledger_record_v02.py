"""Pure backward-compatible notification Ledger record v0.2 codec."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any

from unattended_job_queue import EVENT_TYPES


RECORD_VERSION = "0.2"
IDENTITY = re.compile(r"[0-9a-f]{64}\Z")
V01_FIELDS = frozenset({
    "ledger_version", "event_identity", "event_type", "delivery_status",
    "recorded_at_utc",
})
V02_FIELDS = V01_FIELDS | frozenset({"incident_identity"})


@dataclass(frozen=True)
class SnapshotValidation:
    record_version: str
    status: str
    v01_count: int | None
    v02_count: int | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class IncidentDeliveryEvidence:
    record_version: str
    status: str
    incident_identity: str | None
    recorded_at_utc: str | None
    evidence_available: bool
    reason_codes: tuple[str, ...]


def _timestamp(value: object) -> datetime | None:
    if type(value) is not str or len(value) > 40 or not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    return parsed if parsed.utcoffset() is not None and \
        parsed.utcoffset().total_seconds() == 0 else None


def _common_valid(record: dict[str, Any]) -> bool:
    return (
        type(record["event_identity"]) is str and
        IDENTITY.fullmatch(record["event_identity"]) is not None and
        type(record["event_type"]) is str and record["event_type"] in EVENT_TYPES and
        record["delivery_status"] == "NOTIFICATION_DELIVERED" and
        _timestamp(record["recorded_at_utc"]) is not None
    )


def validate_record(record: object) -> str | None:
    if type(record) is not dict:
        return None
    if set(record) == V01_FIELDS and record.get("ledger_version") == "0.1":
        return "0.1" if _common_valid(record) else None
    if set(record) == V02_FIELDS and record.get("ledger_version") == RECORD_VERSION:
        if not _common_valid(record):
            return None
        incident = record["incident_identity"]
        return RECORD_VERSION if type(incident) is str and \
            IDENTITY.fullmatch(incident) is not None else None
    return None


def build_record(*, event_identity: object, incident_identity: object,
                 event_type: object, recorded_at_utc: object) -> dict[str, Any] | None:
    record = {
        "ledger_version": RECORD_VERSION,
        "event_identity": event_identity,
        "incident_identity": incident_identity,
        "event_type": event_type,
        "delivery_status": "NOTIFICATION_DELIVERED",
        "recorded_at_utc": recorded_at_utc,
    }
    return record if validate_record(record) == RECORD_VERSION else None


def validate_snapshot(records: object) -> SnapshotValidation:
    invalid = SnapshotValidation(
        RECORD_VERSION, "SNAPSHOT_INVALID", None, None,
        ("LEDGER_RECORD_SNAPSHOT_INVALID",),
    )
    if type(records) is not list:
        return invalid
    versions = [validate_record(record) for record in records]
    if any(version is None for version in versions):
        return invalid
    identities = [record["event_identity"] for record in records]
    if len(identities) != len(set(identities)):
        return SnapshotValidation(
            RECORD_VERSION, "SNAPSHOT_INVALID", None, None,
            ("LEDGER_EVENT_IDENTITY_DUPLICATE",),
        )
    return SnapshotValidation(
        RECORD_VERSION, "SNAPSHOT_VALID", versions.count("0.1"),
        versions.count(RECORD_VERSION), ("LEDGER_RECORD_VERSIONS_RECOGNIZED",),
    )


def latest_incident_delivery(records: object,
                             incident_identity: object) -> IncidentDeliveryEvidence:
    if type(incident_identity) is not str or IDENTITY.fullmatch(
            incident_identity) is None:
        return IncidentDeliveryEvidence(
            RECORD_VERSION, "EVIDENCE_INVALID", None, None, False,
            ("INCIDENT_IDENTITY_INVALID",),
        )
    validated = validate_snapshot(records)
    if validated.status != "SNAPSHOT_VALID":
        return IncidentDeliveryEvidence(
            RECORD_VERSION, "EVIDENCE_BLOCKED", incident_identity, None, False,
            validated.reason_codes,
        )
    matches = [record for record in records
               if record.get("ledger_version") == RECORD_VERSION and
               record.get("incident_identity") == incident_identity]
    if not matches:
        return IncidentDeliveryEvidence(
            RECORD_VERSION, "NO_V02_EVIDENCE", incident_identity, None, False,
            ("INCIDENT_DELIVERY_NOT_RECORDED_IN_V02",),
        )
    latest = max(matches, key=lambda record: _timestamp(record["recorded_at_utc"]))
    return IncidentDeliveryEvidence(
        RECORD_VERSION, "EVIDENCE_AVAILABLE", incident_identity,
        latest["recorded_at_utc"], True, ("LATEST_INCIDENT_DELIVERY_FOUND",),
    )


__all__ = [
    "IncidentDeliveryEvidence", "RECORD_VERSION", "SnapshotValidation",
    "build_record", "latest_incident_delivery", "validate_record",
    "validate_snapshot",
]
