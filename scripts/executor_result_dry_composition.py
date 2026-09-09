"""Pure dry selection of an allowlisted durable result coordinator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import durable_job_completion_coordinator as completion
import durable_job_failed_safe_coordinator as failed_safe
import executor_result_coordinator_input_adapter as adapter


COMPOSITION_VERSION = "0.1"
_ALLOWLIST = {
    ("DURABLE_JOB_COMPLETION_COORDINATOR", "complete_running_job_durably"):
        completion.complete_running_job_durably,
    ("DURABLE_JOB_FAILED_SAFE_COORDINATOR", "fail_running_job_durably"):
        failed_safe.fail_running_job_durably,
}


@dataclass(frozen=True)
class DryCompositionResult:
    composition_version: str
    status: str
    selected_route: str
    selected_operation: str | None
    callable_identity_validated: bool
    expected_job_id: str | None
    expected_attempt_count: int | None
    invocation_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **{key: value for key, value in self.__dict__.items()
               if key != "reason_codes"},
            "reason_codes": list(self.reason_codes),
        }


def _blocked(reason: str) -> DryCompositionResult:
    return DryCompositionResult(
        COMPOSITION_VERSION, "DRY_COMPOSITION_BLOCKED", "NONE", None,
        False, None, None, False, (reason,))


def compose_dry(value: Any, *, coordinator_callable: Callable[..., Any] | Any
                ) -> DryCompositionResult:
    """Validate one exact callable selection; never return or invoke it."""
    try:
        if not adapter.validate_coordinator_input(value):
            return _blocked("COORDINATOR_INPUT_INVALID")
        expected = _ALLOWLIST.get((value.route, value.operation))
        if expected is None or coordinator_callable is not expected:
            return _blocked("COORDINATOR_CALLABLE_NOT_ALLOWLISTED")
        return DryCompositionResult(
            COMPOSITION_VERSION, "DRY_COMPOSITION_READY", value.route,
            value.operation, True, value.expected_job_id,
            value.expected_attempt_count, False,
            ("DRY_COORDINATOR_SELECTED",))
    except Exception:
        return _blocked("INTERNAL_COMPOSITION_ERROR")


__all__ = ["COMPOSITION_VERSION", "DryCompositionResult", "compose_dry"]
