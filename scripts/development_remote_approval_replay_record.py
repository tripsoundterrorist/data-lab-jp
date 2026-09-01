"""Pure codec for consumed Codex Remote approval replay evidence."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import development_gate_evidence as evidence_core
import development_gate_coordinator as coordinator
import development_remote_iphone_approval_observation as approval_core


RECORD_VERSION = "0.1"
RECORD_FIELDS = frozenset({
    "record_version", "observation_version", "source", "repository",
    "device_class", "request_id", "current_gate_id", "next_gate_id",
    "head_sha", "ci_run_id", "decision_status", "decided_at_epoch_s",
})
COMMIT_SHA = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True)
class ReplaySnapshotValidation:
    record_version: str
    status: str
    record_count: int | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class ReplayEvidence:
    record_version: str
    status: str
    request_id: str | None
    consumed: bool
    reason_codes: tuple[str, ...]


def _valid_identifier(value: object, pattern: re.Pattern[str]) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def validate_record(record: object) -> bool:
    """Recognize only one exact, sanitized approved-observation record."""
    if type(record) is not dict or set(record) != RECORD_FIELDS:
        return False
    return (
        record["record_version"] == RECORD_VERSION and
        record["observation_version"] == approval_core.OBSERVATION_VERSION and
        record["source"] == approval_core.APPROVED_SOURCE and
        record["repository"] == approval_core.APPROVED_REPOSITORY and
        record["device_class"] == approval_core.APPROVED_DEVICE_CLASS and
        _valid_identifier(record["request_id"], approval_core.REQUEST_ID) and
        _valid_identifier(record["current_gate_id"], evidence_core.GATE_ID) and
        _valid_identifier(record["next_gate_id"], evidence_core.GATE_ID) and
        record["current_gate_id"] != record["next_gate_id"] and
        _valid_identifier(record["head_sha"], COMMIT_SHA) and
        type(record["ci_run_id"]) is int and record["ci_run_id"] > 0 and
        record["decision_status"] == "APPROVED" and
        type(record["decided_at_epoch_s"]) is int and
        record["decided_at_epoch_s"] >= 0
    )


def build_record(observation: object,
                 action_result: object) -> dict[str, Any] | None:
    """Build only from the exact successful existing observation result."""
    if (not isinstance(observation, approval_core.RemoteApprovalObservation) or
            not isinstance(action_result, coordinator.DevelopmentGateActionResult) or
            action_result.result_version !=
            coordinator.ACTION_RESULT_VERSION or
            action_result.action != "REQUEST_APPROVAL" or
            action_result.status != coordinator.ACTION_SUCCEEDED or
            action_result.reason_codes !=
            ("REMOTE_IPHONE_APPROVAL_VALIDATED",) or
            not isinstance(
                action_result.evidence, evidence_core.DevelopmentGateEvidence
            )):
        return None
    evidence = action_result.evidence
    if (evidence_core.evaluate(evidence).status != "NEXT_GATE_READY" or
            evidence.approval_status != "APPROVED" or
            observation.current_gate_id != evidence.current_gate_id or
            observation.next_gate_id != evidence.next_gate_id or
            observation.head_sha != evidence.commit_sha or
            observation.ci_run_id != evidence.ci_run_id):
        return None
    record = {
        "record_version": RECORD_VERSION,
        "observation_version": observation.observation_version,
        "source": observation.source,
        "repository": observation.repository,
        "device_class": observation.device_class,
        "request_id": observation.request_id,
        "current_gate_id": observation.current_gate_id,
        "next_gate_id": observation.next_gate_id,
        "head_sha": observation.head_sha,
        "ci_run_id": observation.ci_run_id,
        "decision_status": observation.status,
        "decided_at_epoch_s": observation.decided_at_epoch_s,
    }
    return record if validate_record(record) else None


def _target(record: dict[str, Any]) -> tuple[object, ...]:
    return (
        record["current_gate_id"], record["next_gate_id"],
        record["head_sha"], record["ci_run_id"],
    )


def validate_snapshot(records: object) -> ReplaySnapshotValidation:
    invalid = ReplaySnapshotValidation(
        RECORD_VERSION, "SNAPSHOT_INVALID", None,
        ("REMOTE_APPROVAL_REPLAY_SNAPSHOT_INVALID",),
    )
    if type(records) is not list or any(
            not validate_record(record) for record in records):
        return invalid
    request_ids = [record["request_id"] for record in records]
    if len(request_ids) != len(set(request_ids)):
        return ReplaySnapshotValidation(
            RECORD_VERSION, "SNAPSHOT_INVALID", None,
            ("REMOTE_APPROVAL_REQUEST_ID_DUPLICATE",),
        )
    targets = [_target(record) for record in records]
    if len(targets) != len(set(targets)):
        return ReplaySnapshotValidation(
            RECORD_VERSION, "SNAPSHOT_INVALID", None,
            ("REMOTE_APPROVAL_TARGET_DUPLICATE",),
        )
    return ReplaySnapshotValidation(
        RECORD_VERSION, "SNAPSHOT_VALID", len(records),
        ("REMOTE_APPROVAL_REPLAY_RECORDS_RECOGNIZED",),
    )


def find_consumed_request(records: object, request_id: object) -> ReplayEvidence:
    if not _valid_identifier(request_id, approval_core.REQUEST_ID):
        return ReplayEvidence(
            RECORD_VERSION, "EVIDENCE_INVALID", None, False,
            ("REMOTE_APPROVAL_REQUEST_ID_INVALID",),
        )
    validated = validate_snapshot(records)
    if validated.status != "SNAPSHOT_VALID":
        return ReplayEvidence(
            RECORD_VERSION, "EVIDENCE_BLOCKED", request_id, False,
            validated.reason_codes,
        )
    consumed = any(record["request_id"] == request_id for record in records)
    return ReplayEvidence(
        RECORD_VERSION,
        "APPROVAL_ALREADY_CONSUMED" if consumed else "APPROVAL_NOT_CONSUMED",
        request_id,
        consumed,
        ("REMOTE_APPROVAL_REPLAY_DETECTED",) if consumed else
        ("REMOTE_APPROVAL_REQUEST_FRESH",),
    )


__all__ = [
    "RECORD_FIELDS", "RECORD_VERSION", "ReplayEvidence",
    "ReplaySnapshotValidation", "build_record", "find_consumed_request",
    "validate_record", "validate_snapshot",
]
