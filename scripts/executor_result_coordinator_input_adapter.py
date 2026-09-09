"""Pure routing adapter for one authenticated executor result."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import executor_result_authentication as authentication


ADAPTER_VERSION = "0.1"
_ROUTES = {
    authentication.COMPLETED: (
        "DURABLE_JOB_COMPLETION_COORDINATOR", "complete_running_job_durably"),
    authentication.FAILED_SAFE: (
        "DURABLE_JOB_FAILED_SAFE_COORDINATOR", "fail_running_job_durably"),
}


@dataclass(frozen=True)
class CoordinatorInput:
    adapter_version: str
    status: str
    route: str
    operation: str | None
    expected_job_id: str | None
    expected_attempt_count: int | None
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **{key: value for key, value in self.__dict__.items()
               if key != "reason_codes"},
            "reason_codes": list(self.reason_codes),
        }


def _blocked(reason: str) -> CoordinatorInput:
    return CoordinatorInput(
        ADAPTER_VERSION, "COORDINATOR_INPUT_BLOCKED", "NONE", None,
        None, None, (reason,))


def validate_coordinator_input(value: Any) -> bool:
    """Validate one ready coordinator input without invoking its route."""
    try:
        expected = _ROUTES.get({
            "DURABLE_JOB_COMPLETION_COORDINATOR": authentication.COMPLETED,
            "DURABLE_JOB_FAILED_SAFE_COORDINATOR": authentication.FAILED_SAFE,
        }.get(value.route))
        return (
            type(value) is CoordinatorInput
            and value.adapter_version == ADAPTER_VERSION
            and value.status == "COORDINATOR_INPUT_READY"
            and expected is not None
            and (value.route, value.operation) == expected
            and authentication.validate_execution_generation(
                value.expected_job_id, value.expected_attempt_count)
            and value.reason_codes == ("COORDINATOR_INPUT_READY",)
        )
    except Exception:
        return False


def adapt_authenticated_executor_result(value: Any) -> CoordinatorInput:
    """Return fixed arguments for exactly one coordinator; invoke nothing."""
    try:
        if not authentication.validate_executor_result_authentication(value):
            return _blocked("AUTHENTICATION_RESULT_INVALID")
        route = _ROUTES.get(value.outcome)
        if route is None:
            return _blocked("AUTHENTICATED_OUTCOME_UNSUPPORTED")
        return CoordinatorInput(
            ADAPTER_VERSION, "COORDINATOR_INPUT_READY", route[0], route[1],
            value.job_id, value.attempt_count, ("COORDINATOR_INPUT_READY",))
    except Exception:
        return _blocked("INTERNAL_ADAPTER_ERROR")


__all__ = [
    "ADAPTER_VERSION", "CoordinatorInput",
    "adapt_authenticated_executor_result", "validate_coordinator_input",
]
