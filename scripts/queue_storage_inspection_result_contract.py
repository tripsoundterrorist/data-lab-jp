"""Pure fail-closed result contract for Queue storage inspection v0.1."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import queue_storage_inspection_payload_schema as schema
import unattended_job_queue as core
import unattended_queue_persistence as persistence


RESULT_CONTRACT_VERSION = "0.1"
MAX_REASON_CODES = 32
SAFE_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
CHECKPOINT_STATUSES = {
    "HEALTHY", "MANUAL_REVIEW_REQUIRED", "MISSING_EMPTY_STORAGE_ALLOWED",
    "RECOVERY_BLOCKED", "UNREFERENCED_OBJECTS_PRESENT",
}
ARTIFACT_STATUSES = {"ABSENT", "PRESENT", "UNKNOWN"}
ACTION_CODES = {"NONE", "OPERATOR_REVIEW", "STOP_QUEUE_RECOVERY"}


@dataclass(frozen=True)
class InspectionResultValidation:
    contract_version: str
    status: str
    result_valid: bool
    execution_allowed: bool
    output_code: str | None
    reason_codes: tuple[str, ...]


def _result(status: str, reasons: tuple[str, ...], *, valid: bool = False,
            output_code: str | None = None) -> InspectionResultValidation:
    return InspectionResultValidation(
        RESULT_CONTRACT_VERSION, status, valid, False, output_code,
        tuple(sorted(set(reasons))))


def _optional_count(value: Any) -> bool:
    return value is None or (type(value) is int and value >= 0)


def _state_counts_valid(value: Any, job_count: int | None) -> bool:
    if type(value) is not tuple:
        return False
    if any(type(item) is not tuple or len(item) != 2 for item in value):
        return False
    if any(type(state) is not str or type(count) is not int or count <= 0
           for state, count in value):
        return False
    states = [item[0] for item in value]
    if states != sorted(states) or len(states) != len(set(states)):
        return False
    if any(state not in core.JOB_STATES for state in states):
        return False
    if job_count is None:
        return value == ()
    return sum(count for _, count in value) == job_count


def _reason_codes_valid(value: Any) -> bool:
    if type(value) is not tuple or not 0 < len(value) <= MAX_REASON_CODES:
        return False
    if any(type(code) is not str or SAFE_CODE.fullmatch(code) is None
           for code in value):
        return False
    return list(value) == sorted(value) and len(value) == len(set(value))


def _count_relationships_valid(value: persistence.ProductionStorageInspectionResult
                               ) -> bool:
    if value.persistence_version is None:
        if (value.revision is not None or value.job_count is not None
                or value.active_reference_count is not None
                or value.state_counts != ()):
            return False
    elif (value.persistence_version != persistence.PERSISTENCE_VERSION
          or value.revision is None or value.job_count is None
          or value.active_reference_count is None):
        return False
    if (value.job_count is not None and value.active_reference_count is not None
            and value.active_reference_count > value.job_count):
        return False
    if (value.checkpoint_object_count is not None
            and value.unreferenced_object_count is not None
            and value.corrupt_unreferenced_count is not None
            and (value.unreferenced_object_count
                 + value.corrupt_unreferenced_count
                 > value.checkpoint_object_count)):
        return False
    active_parts = (
        value.missing_reference_count, value.mismatched_reference_count,
        value.corrupt_active_count,
    )
    if (value.active_reference_count is not None
            and all(item is not None for item in active_parts)
            and sum(active_parts) > value.active_reference_count):
        return False
    return value.confirmed_orphan_count is None


def _semantics_valid(value: persistence.ProductionStorageInspectionResult
                     ) -> bool:
    if value.status == "HEALTHY":
        return (
            value.persistence_version == persistence.PERSISTENCE_VERSION
            and value.queue_exists
            and value.lock_status == "ABSENT"
            and value.temp_status == "ABSENT"
            and value.action_required == "NONE"
            and value.checkpoint_status in {
                "HEALTHY", "MISSING_EMPTY_STORAGE_ALLOWED",
                "UNREFERENCED_OBJECTS_PRESENT",
            }
        )
    if value.status == "MISSING_REQUIRES_BOOTSTRAP":
        return (
            value.persistence_version is None
            and not value.queue_exists
            and value.lock_status == "ABSENT"
            and value.temp_status == "ABSENT"
            and value.action_required == "NONE"
            and value.checkpoint_status != "RECOVERY_BLOCKED"
        )
    if value.status == "LOCKED":
        return value.lock_status == "PRESENT" and value.action_required == "OPERATOR_REVIEW"
    if value.status == "MANUAL_REVIEW_REQUIRED":
        return value.action_required == "OPERATOR_REVIEW"
    if value.status == "RECOVERY_BLOCKED":
        return value.action_required in {"OPERATOR_REVIEW", "STOP_QUEUE_RECOVERY"}
    return False


def validate_result(value: Any) -> InspectionResultValidation:
    """Validate an already-produced safe aggregate result; never inspect storage."""
    try:
        if type(value) is not persistence.ProductionStorageInspectionResult:
            return _result(
                "INSPECTION_RESULT_REJECTED", ("RESULT_CONTRACT_INVALID",))
        reasons: list[str] = []
        if value.result_version != persistence.RESULT_VERSION:
            reasons.append("RESULT_VERSION_UNSUPPORTED")
        if value.status not in schema.OUTPUT_CODES:
            reasons.append("OUTPUT_CODE_NOT_ALLOWED")
        counts = (
            value.revision, value.job_count, value.active_reference_count,
            value.checkpoint_object_count, value.unreferenced_object_count,
            value.confirmed_orphan_count, value.missing_reference_count,
            value.mismatched_reference_count, value.corrupt_active_count,
            value.corrupt_unreferenced_count,
        )
        fields_valid = (
            (value.persistence_version is None
             or type(value.persistence_version) is str)
            and type(value.checkpoint_status) is str
            and value.checkpoint_status in CHECKPOINT_STATUSES
            and type(value.queue_exists) is bool
            and type(value.checkpoint_storage_exists) is bool
            and all(_optional_count(item) for item in counts)
            and _state_counts_valid(value.state_counts, value.job_count)
            and type(value.lock_status) is str
            and value.lock_status in ARTIFACT_STATUSES
            and type(value.temp_status) is str
            and value.temp_status in ARTIFACT_STATUSES
            and type(value.action_required) is str
            and value.action_required in ACTION_CODES
            and _reason_codes_valid(value.reason_codes)
            and _count_relationships_valid(value)
        )
        if not fields_valid:
            reasons.append("RESULT_FIELDS_INVALID")
        if value.status in schema.OUTPUT_CODES and not _semantics_valid(value):
            reasons.append("RESULT_SEMANTICS_INVALID")
        if reasons:
            return _result("INSPECTION_RESULT_REJECTED", tuple(reasons))
        return _result(
            "INSPECTION_RESULT_ACCEPTED", ("INSPECTION_OUTPUT_ALLOWED",),
            valid=True, output_code=value.status)
    except Exception:
        return _result(
            "INSPECTION_RESULT_REJECTED",
            ("RESULT_VALIDATION_INTERNAL_ERROR",))
