"""Candidate schema for one local read-only Queue inspection job."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import queue_input_job_payload_contract as inputs
import unattended_job_queue as core


SCHEMA_VERSION = "0.1"
JOB_TYPE = "queue_storage_inspection"
PAYLOAD_MODE = "LOCAL_READ_ONLY"
PROVENANCE = "BUILTIN_POLICY"
MAX_RUNTIME_SECONDS = 5
PREFLIGHT_CODES = ("PRODUCTION_WRITE_DISABLED", "QUEUE_IDENTITY_VALID")
OUTPUT_CODES = (
    "HEALTHY", "LOCKED", "MANUAL_REVIEW_REQUIRED",
    "MISSING_REQUIRES_BOOTSTRAP", "RECOVERY_BLOCKED",
)


@dataclass(frozen=True)
class QueueStorageInspectionPayloadSchema:
    schema_version: str
    job_type: str
    payload_mode: str
    provenance: str
    parameter_codes: tuple[str, ...]
    preflight_codes: tuple[str, ...]
    max_runtime_seconds: int
    output_codes: tuple[str, ...]


@dataclass(frozen=True)
class PayloadSchemaValidationResult:
    schema_version: str
    status: str
    schema_valid: bool
    execution_allowed: bool
    reason_codes: tuple[str, ...]


def get_schema() -> QueueStorageInspectionPayloadSchema:
    return QueueStorageInspectionPayloadSchema(
        SCHEMA_VERSION, JOB_TYPE, PAYLOAD_MODE, PROVENANCE, (),
        PREFLIGHT_CODES, MAX_RUNTIME_SECONDS, OUTPUT_CODES)


def _result(status: str, reasons: tuple[str, ...], *, valid: bool = False
            ) -> PayloadSchemaValidationResult:
    return PayloadSchemaValidationResult(
        SCHEMA_VERSION, status, valid, False, reasons)


def validate_candidate(job: Any, payload: Any, schema: Any
                       ) -> PayloadSchemaValidationResult:
    """Validate the candidate schema without admitting or executing the job."""
    try:
        if type(schema) is not QueueStorageInspectionPayloadSchema or schema != get_schema():
            return _result("PAYLOAD_SCHEMA_REJECTED", ("SCHEMA_CONTRACT_INVALID",))
        if type(job) is not core.JobContract or not core.validate_job(job)[0]:
            return _result("PAYLOAD_SCHEMA_REJECTED", ("JOB_CONTRACT_INVALID",))
        if (job.job_type != JOB_TYPE or job.risk_class != core.READ_ONLY
                or job.state != core.READY or job.attempt_count != 0
                or job.approval_received or job.requires_approval
                or job.dependencies or job.blocker_codes):
            return _result("PAYLOAD_SCHEMA_REJECTED", ("JOB_PROFILE_INVALID",))
        if type(payload) is not inputs.JobPayloadContract:
            return _result("PAYLOAD_SCHEMA_REJECTED", ("PAYLOAD_CONTRACT_INVALID",))
        if (payload.payload_version != inputs.PAYLOAD_CONTRACT_VERSION
                or payload.job_id != job.job_id or payload.job_type != JOB_TYPE):
            return _result("PAYLOAD_SCHEMA_REJECTED", ("PAYLOAD_JOB_BINDING_INVALID",))
        if payload.payload_mode != PAYLOAD_MODE or payload.parameter_codes != ():
            return _result("PAYLOAD_SCHEMA_REJECTED", ("PAYLOAD_PARAMETERS_INVALID",))
        return _result("PAYLOAD_SCHEMA_VALID", ("LOCAL_READ_ONLY_SCHEMA_VALID",),
                       valid=True)
    except Exception:
        return _result("PAYLOAD_SCHEMA_REJECTED", ("SCHEMA_VALIDATION_INTERNAL_ERROR",))
