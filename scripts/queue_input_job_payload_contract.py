"""Pure fail-closed Queue input and non-executable payload contract v0.1."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import unattended_job_queue as core


INPUT_CONTRACT_VERSION = "0.1"
PAYLOAD_CONTRACT_VERSION = "0.1"
NO_PAYLOAD = "NO_PAYLOAD"
MAX_INPUT_JOBS = 256
SAFE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
FORBIDDEN = re.compile(
    r"(?i)(?:api|affiliate)[_-]?id|credential|password|secret|token|"
    r"payload|command|argument|handler|raw|traceback|title|url|path"
)


@dataclass(frozen=True)
class JobPayloadContract:
    payload_version: str
    job_id: str
    job_type: str
    payload_mode: str
    parameter_codes: tuple[str, ...]


@dataclass(frozen=True)
class QueueInputContract:
    input_version: str
    queue_identity: core.QueueIdentity
    jobs: tuple[core.JobContract, ...]
    payloads: tuple[JobPayloadContract, ...]


@dataclass(frozen=True)
class QueueInputValidationResult:
    contract_version: str
    status: str
    admission_allowed: bool
    execution_allowed: bool
    job_count: int | None
    reason_codes: tuple[str, ...]


def _safe_token(value: Any) -> bool:
    return (type(value) is str and SAFE_TOKEN.fullmatch(value) is not None
            and FORBIDDEN.search(value) is None)


def _result(status: str, reasons: tuple[str, ...], *, allowed: bool = False,
            job_count: int | None = None) -> QueueInputValidationResult:
    return QueueInputValidationResult(
        INPUT_CONTRACT_VERSION, status, allowed, False, job_count, reasons)


def validate_queue_input(value: Any) -> QueueInputValidationResult:
    """Validate typed fresh admission metadata; never authorize execution."""
    try:
        if type(value) is not QueueInputContract:
            return _result("QUEUE_INPUT_REJECTED", ("INPUT_CONTRACT_INVALID",))
        reasons: list[str] = []
        if value.input_version != INPUT_CONTRACT_VERSION:
            reasons.append("INPUT_VERSION_UNSUPPORTED")
        if not core.validate_queue_identity(value.queue_identity):
            reasons.append("QUEUE_IDENTITY_INVALID")
        if type(value.jobs) is not tuple or not value.jobs:
            reasons.append("INPUT_JOBS_INVALID")
        elif len(value.jobs) > MAX_INPUT_JOBS:
            reasons.append("INPUT_JOB_LIMIT_EXCEEDED")
        else:
            valid, queue_reasons = core.validate_queue(value.jobs)
            if not valid:
                reasons.extend(queue_reasons)
            for job in value.jobs:
                if (job.state != core.READY or job.attempt_count != 0
                        or job.approval_received):
                    reasons.append("FRESH_JOB_STATE_REQUIRED")
        if type(value.payloads) is not tuple:
            reasons.append("PAYLOAD_SET_INVALID")
        elif type(value.jobs) is tuple:
            job_ids = [job.job_id for job in value.jobs]
            payload_ids = [item.job_id for item in value.payloads
                           if type(item) is JobPayloadContract]
            if any(type(item) is not JobPayloadContract for item in value.payloads):
                reasons.append("PAYLOAD_CONTRACT_INVALID")
            if payload_ids != sorted(payload_ids):
                reasons.append("PAYLOAD_ORDER_INVALID")
            if len(payload_ids) != len(set(payload_ids)):
                reasons.append("PAYLOAD_DUPLICATE")
            if set(payload_ids) != set(job_ids) or len(value.payloads) != len(value.jobs):
                reasons.append("PAYLOAD_JOB_SET_MISMATCH")
            jobs = {job.job_id: job for job in value.jobs
                    if type(job) is core.JobContract}
            for item in value.payloads:
                if type(item) is not JobPayloadContract:
                    continue
                job = jobs.get(item.job_id)
                if (item.payload_version != PAYLOAD_CONTRACT_VERSION
                        or not _safe_token(item.job_id)
                        or not _safe_token(item.job_type)):
                    reasons.append("PAYLOAD_CONTRACT_INVALID")
                if job is None or item.job_type != job.job_type:
                    reasons.append("PAYLOAD_JOB_BINDING_INVALID")
                if item.payload_mode != NO_PAYLOAD or item.parameter_codes != ():
                    reasons.append("EXECUTABLE_PAYLOAD_NOT_AUTHORIZED")
        if reasons:
            return _result("QUEUE_INPUT_REJECTED",
                           tuple(sorted(set(reasons))))
        return _result("QUEUE_INPUT_ACCEPTED", ("NON_EXECUTABLE_INPUT_VALID",),
                       allowed=True, job_count=len(value.jobs))
    except Exception:
        return _result("QUEUE_INPUT_REJECTED", ("INPUT_VALIDATION_INTERNAL_ERROR",))
