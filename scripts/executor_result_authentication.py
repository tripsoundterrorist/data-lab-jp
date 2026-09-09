"""Pure fail-closed contract authentication for one adopted execution result."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import durable_execution_adoption_coordinator as adoption


AUTHENTICATION_VERSION = "0.1"
EVIDENCE_VERSION = "0.1"
COMPLETED = "COMPLETED"
FAILED_SAFE = "FAILED_SAFE"
OUTCOMES = frozenset({COMPLETED, FAILED_SAFE})

_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_SECRET_LIKE = re.compile(
    r"(?i)(?:secret|token|password|credential|api[_-]?key|private[_-]?key)")
_RESULT_CODES = {
    COMPLETED: "EXECUTOR_CONFIRMED_COMPLETION",
    FAILED_SAFE: "EXECUTOR_CONFIRMED_SAFE_FAILURE",
}
_ACTIONS = {
    COMPLETED: "COMPLETE_JOB_DURABLY",
    FAILED_SAFE: "FAIL_JOB_SAFE_DURABLY",
}


@dataclass(frozen=True)
class ExecutorResultEvidence:
    evidence_version: str
    job_id: str
    attempt_count: int
    outcome: str
    result_code: str


@dataclass(frozen=True)
class ExecutorResultAuthentication:
    authentication_version: str
    status: str
    authenticated: bool
    job_id: str | None
    attempt_count: int | None
    outcome: str | None
    next_action: str
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **{key: value for key, value in self.__dict__.items()
               if key != "reason_codes"},
            "reason_codes": list(self.reason_codes),
        }


def _rejected(reason: str) -> ExecutorResultAuthentication:
    return ExecutorResultAuthentication(
        AUTHENTICATION_VERSION, "AUTHENTICATION_REJECTED", False,
        None, None, None, "NONE", (reason,))


def _safe_id(value: Any) -> bool:
    return (type(value) is str and _SAFE_ID.fullmatch(value) is not None
            and _SECRET_LIKE.search(value) is None)


def validate_execution_generation(job_id: Any, attempt_count: Any) -> bool:
    """Validate the shared safe execution-generation fields."""
    return (_safe_id(job_id) and type(attempt_count) is int
            and attempt_count >= 1)


def validate_executor_result_authentication(result: Any) -> bool:
    """Validate one successful authentication result without side effects."""
    try:
        return (
            type(result) is ExecutorResultAuthentication
            and result.authentication_version == AUTHENTICATION_VERSION
            and result.status == "EXECUTOR_RESULT_AUTHENTICATED"
            and result.authenticated is True
            and validate_execution_generation(result.job_id, result.attempt_count)
            and result.outcome in OUTCOMES
            and result.next_action == _ACTIONS.get(result.outcome)
            and result.reason_codes == ("EXECUTOR_RESULT_AUTHENTICATED",)
        )
    except Exception:
        return False


def authenticate_executor_result(
    adopted: Any, evidence: Any, *, expected_job_id: Any,
    expected_attempt_count: Any,
) -> ExecutorResultAuthentication:
    """Authenticate fixed result evidence against one durable adoption result.

    This is pure contract authentication, not cryptographic origin attestation.
    """
    try:
        if (type(expected_attempt_count) is not int
                or expected_attempt_count < 1 or not _safe_id(expected_job_id)):
            return _rejected("EXPECTED_GENERATION_INVALID")
        if type(adopted) is not adoption.DurableExecutionAdoptionResult:
            return _rejected("ADOPTION_EVIDENCE_INVALID")
        if (adopted.coordinator_version != adoption.COORDINATOR_VERSION
                or adopted.status != "EXECUTION_ADOPTED_DURABLY"
                or adopted.durable is not True
                or adopted.reason_codes != ("EXECUTION_ADOPTION_DURABLE",)
                or not _safe_id(adopted.job_id)
                or type(adopted.attempt_count) is not int
                or adopted.attempt_count < 1
                or type(adopted.revision) is not int or adopted.revision < 1):
            return _rejected("ADOPTION_EVIDENCE_INVALID")
        if (adopted.job_id != expected_job_id
                or adopted.attempt_count != expected_attempt_count):
            return _rejected("ADOPTED_GENERATION_MISMATCH")
        if type(evidence) is not ExecutorResultEvidence:
            return _rejected("EXECUTOR_RESULT_EVIDENCE_INVALID")
        if (evidence.evidence_version != EVIDENCE_VERSION
                or not _safe_id(evidence.job_id)
                or type(evidence.attempt_count) is not int
                or evidence.attempt_count < 1
                or type(evidence.outcome) is not str
                or evidence.outcome not in OUTCOMES
                or type(evidence.result_code) is not str
                or evidence.result_code != _RESULT_CODES.get(evidence.outcome)):
            return _rejected("EXECUTOR_RESULT_EVIDENCE_INVALID")
        if (evidence.job_id != expected_job_id
                or evidence.attempt_count != expected_attempt_count):
            return _rejected("EXECUTOR_RESULT_GENERATION_MISMATCH")
        return ExecutorResultAuthentication(
            AUTHENTICATION_VERSION, "EXECUTOR_RESULT_AUTHENTICATED", True,
            expected_job_id, expected_attempt_count, evidence.outcome,
            _ACTIONS[evidence.outcome], ("EXECUTOR_RESULT_AUTHENTICATED",))
    except Exception:
        return _rejected("INTERNAL_AUTHENTICATION_ERROR")


__all__ = [
    "AUTHENTICATION_VERSION", "COMPLETED", "EVIDENCE_VERSION", "FAILED_SAFE",
    "OUTCOMES", "ExecutorResultAuthentication", "ExecutorResultEvidence",
    "authenticate_executor_result", "validate_executor_result_authentication",
    "validate_execution_generation",
]
