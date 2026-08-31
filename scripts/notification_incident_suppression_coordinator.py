"""Pure coordinator for v0.2 incident evidence and notification noise policy."""

from __future__ import annotations

from dataclasses import dataclass

import notification_ledger_record_v02 as ledger_codec
import notification_noise_control as noise_policy


COORDINATOR_VERSION = "0.1"


@dataclass(frozen=True)
class IncidentSuppressionDecision:
    coordinator_version: str
    status: str
    action: str
    delivery_allowed: bool
    reminder: bool
    evidence_status: str
    reason_codes: tuple[str, ...]


def _blocked(evidence_status: str, *reasons: str) -> IncidentSuppressionDecision:
    return IncidentSuppressionDecision(
        COORDINATOR_VERSION, "COORDINATION_BLOCKED", "NONE", False, False,
        evidence_status, tuple(reasons),
    )


def coordinate(*, records: object, event_type: object,
               incident_identity: object,
               occurred_at: object) -> IncidentSuppressionDecision:
    """Select delivery from recognized evidence; never infer from v0.1."""

    evidence = ledger_codec.latest_incident_delivery(records, incident_identity)
    if evidence.status in {"EVIDENCE_INVALID", "EVIDENCE_BLOCKED"}:
        return _blocked(evidence.status, *evidence.reason_codes)
    if evidence.status not in {"NO_V02_EVIDENCE", "EVIDENCE_AVAILABLE"}:
        return _blocked("EVIDENCE_UNRECOGNIZED", "INCIDENT_EVIDENCE_STATUS_INVALID")

    previous_key = evidence.incident_identity if evidence.evidence_available else None
    previous_at = evidence.recorded_at_utc if evidence.evidence_available else None
    decision = noise_policy.evaluate(noise_policy.NotificationNoiseEvidence(
        event_type=event_type,
        event_key=incident_identity,
        occurred_at=occurred_at,
        last_delivered_event_key=previous_key,
        last_delivered_at=previous_at,
    ))
    if decision.status == "INVALID_INPUT":
        return _blocked(evidence.status, *decision.reason_codes)
    return IncidentSuppressionDecision(
        COORDINATOR_VERSION, decision.status, decision.action,
        decision.delivery_allowed, decision.reminder, evidence.status,
        evidence.reason_codes + decision.reason_codes,
    )


__all__ = [
    "COORDINATOR_VERSION", "IncidentSuppressionDecision", "coordinate",
]
