"""Pure Queue Input integration for the storage inspection schema v0.1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import queue_input_job_payload_contract as inputs
import queue_storage_inspection_payload_schema as inspection
import unattended_job_queue as core


INTEGRATION_CONTRACT_VERSION = "0.1"


@dataclass(frozen=True)
class QueueInputIntegrationResult:
    contract_version: str
    status: str
    admission_allowed: bool
    execution_allowed: bool
    job_count: int | None
    recognized_schema_count: int
    reason_codes: tuple[str, ...]


def _result(status: str, reasons: tuple[str, ...], *, allowed: bool = False,
            job_count: int | None = None, recognized: int = 0
            ) -> QueueInputIntegrationResult:
    return QueueInputIntegrationResult(
        INTEGRATION_CONTRACT_VERSION, status, allowed, False, job_count,
        recognized, tuple(sorted(set(reasons))))


def _admission_payload(payload: inputs.JobPayloadContract
                       ) -> inputs.JobPayloadContract:
    return inputs.JobPayloadContract(
        payload.payload_version, payload.job_id, payload.job_type,
        inputs.NO_PAYLOAD, ())


def validate_queue_input(value: Any) -> QueueInputIntegrationResult:
    """Recognize the exact built-in schema while never authorizing execution."""
    try:
        if type(value) is not inputs.QueueInputContract:
            base = inputs.validate_queue_input(value)
            return _result(base.status, base.reason_codes)

        jobs = {}
        if type(value.jobs) is tuple:
            jobs = {
                job.job_id: job for job in value.jobs
                if type(job) is core.JobContract
            }

        normalized: list[Any] = []
        schema_reasons: list[str] = []
        recognized = 0
        if type(value.payloads) is tuple:
            for payload in value.payloads:
                if type(payload) is not inputs.JobPayloadContract:
                    normalized.append(payload)
                    continue
                schema_routed = (
                    payload.job_type == inspection.JOB_TYPE
                    or payload.payload_mode == inspection.PAYLOAD_MODE
                )
                if not schema_routed:
                    normalized.append(payload)
                    continue
                candidate = inspection.validate_candidate(
                    jobs.get(payload.job_id), payload, inspection.get_schema())
                if not candidate.schema_valid:
                    schema_reasons.append(
                        "QUEUE_STORAGE_INSPECTION_SCHEMA_INVALID")
                    schema_reasons.extend(candidate.reason_codes)
                    normalized.append(payload)
                    continue
                normalized.append(_admission_payload(payload))
                recognized += 1
        else:
            normalized = []

        admission_view = inputs.QueueInputContract(
            value.input_version, value.queue_identity, value.jobs,
            tuple(normalized) if type(value.payloads) is tuple else value.payloads)
        base = inputs.validate_queue_input(admission_view)
        if not base.admission_allowed or schema_reasons:
            return _result(
                "QUEUE_INPUT_REJECTED",
                base.reason_codes + tuple(schema_reasons),
                recognized=recognized)

        reasons = list(base.reason_codes)
        if recognized:
            reasons.append("QUEUE_STORAGE_INSPECTION_SCHEMA_RECOGNIZED")
        return _result(
            base.status, tuple(reasons), allowed=True,
            job_count=base.job_count, recognized=recognized)
    except Exception:
        return _result(
            "QUEUE_INPUT_REJECTED", ("INPUT_INTEGRATION_INTERNAL_ERROR",))
