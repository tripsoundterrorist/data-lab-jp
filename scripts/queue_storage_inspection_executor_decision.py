"""Pure blocked Executor decision for Queue storage inspection v0.1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import queue_input_storage_inspection_integration as queue_integration
import queue_storage_inspection_payload_schema as schema
import queue_storage_inspection_result_contract as result_contract


EXECUTOR_DECISION_VERSION = "0.1"


@dataclass(frozen=True)
class ExecutorDecision:
    decision_version: str
    status: str
    boundaries_valid: bool
    invocation_allowed: bool
    production_write_allowed: bool
    attempt_update_allowed: bool
    max_runtime_seconds: int | None
    output_code: str | None
    reason_codes: tuple[str, ...]


def _decision(status: str, reasons: tuple[str, ...], *, valid: bool = False,
              output_code: str | None = None) -> ExecutorDecision:
    return ExecutorDecision(
        EXECUTOR_DECISION_VERSION, status, valid, False, False, False,
        schema.MAX_RUNTIME_SECONDS if valid else None,
        output_code if valid else None, tuple(sorted(set(reasons))))


def decide(queue_input: Any, inspection_result: Any) -> ExecutorDecision:
    """Validate both boundaries while retaining a closed activation gate."""
    try:
        admission = queue_integration.validate_queue_input(queue_input)
        validated_result = result_contract.validate_result(inspection_result)
        reasons: list[str] = []
        if not admission.admission_allowed:
            reasons.append("QUEUE_INPUT_NOT_ADMITTED")
        elif (admission.job_count != 1
              or admission.recognized_schema_count != 1):
            reasons.append("TARGET_SCHEMA_NOT_EXCLUSIVE")
        if not validated_result.result_valid:
            reasons.append("INSPECTION_RESULT_NOT_ACCEPTED")
        if reasons:
            return _decision("EXECUTOR_DECISION_REJECTED", tuple(reasons))
        return _decision(
            "EXECUTOR_ACTIVATION_BLOCKED",
            ("SEPARATE_ACTIVATION_GATE_REQUIRED",), valid=True,
            output_code=validated_result.output_code)
    except Exception:
        return _decision(
            "EXECUTOR_DECISION_REJECTED",
            ("EXECUTOR_DECISION_INTERNAL_ERROR",))
