"""Single-action, default-disabled coordinator for development Gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

import development_gate_evidence as core


COORDINATOR_VERSION = "0.1"
ACTION_RESULT_VERSION = "0.1"
ACTION_SUCCEEDED = "SUCCEEDED"
ACTION_FAILED = "FAILED"
ACTION_UNCERTAIN = "UNCERTAIN"

_TEST_TOKEN = object()
_EXPECTED_AFTER = {
    "SAVE_CHECKPOINT": frozenset({"TEST_REQUIRED"}),
    "RUN_TESTS": frozenset({"COMMIT_PUSH_REQUIRED"}),
    "COMMIT_AND_PUSH": frozenset({"CI_REQUIRED"}),
    "WAIT_FOR_CI": frozenset({"APPROVAL_REQUIRED", "NEXT_GATE_READY"}),
    "REQUEST_APPROVAL": frozenset({"NEXT_GATE_READY"}),
}


@dataclass(frozen=True)
class DevelopmentGateActionResult:
    result_version: str
    action: str
    status: str
    evidence: core.DevelopmentGateEvidence | None
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class DevelopmentGateCoordinatorResult:
    coordinator_version: str
    status: str
    planned_action: str
    action_invoked: bool
    next_gate_started: bool
    before_status: str
    after_status: str | None
    reason_codes: tuple[str, ...]


Adapter = Callable[[core.DevelopmentGateEvidence], DevelopmentGateActionResult]


def _result(status: str, action: str, invoked: bool, started: bool,
            before: str, after: str | None,
            *reasons: str) -> DevelopmentGateCoordinatorResult:
    return DevelopmentGateCoordinatorResult(
        COORDINATOR_VERSION, status, action, invoked, started, before, after,
        tuple(reasons),
    )


class DevelopmentGateCoordinator:
    """Production construction is disabled; enabled adapters are test-scoped."""

    def __init__(self, adapters: Mapping[str, Adapter] | None = None,
                 token: object | None = None):
        self._enabled = token is _TEST_TOKEN
        self._adapters = dict(adapters or {}) if self._enabled else {}

    @classmethod
    def disabled(cls) -> "DevelopmentGateCoordinator":
        return cls()

    @classmethod
    def _for_test(cls, adapters: Mapping[str, Adapter]) -> "DevelopmentGateCoordinator":
        return cls(adapters, _TEST_TOKEN)

    def coordinate(self, evidence: object) -> DevelopmentGateCoordinatorResult:
        decision = core.evaluate(evidence)
        if decision.status == "EVIDENCE_REJECTED":
            return _result("COORDINATION_REJECTED", "NONE", False, False,
                           decision.status, None, *decision.reason_codes)
        if not self._enabled:
            return _result("AUTOMATION_DISABLED", decision.next_action, False,
                           False, decision.status, None,
                           "DEVELOPMENT_AUTOMATION_DISABLED")

        adapter = self._adapters.get(decision.next_action)
        if not callable(adapter):
            return _result("COORDINATION_BLOCKED", decision.next_action, False,
                           False, decision.status, None, "ACTION_ADAPTER_UNAVAILABLE")

        try:
            action_result = adapter(evidence)
        except Exception:
            return _result("ACTION_FAILED_SAFE", decision.next_action, True,
                           False, decision.status, None, "ACTION_ADAPTER_EXCEPTION")

        if not isinstance(action_result, DevelopmentGateActionResult):
            return _result("ACTION_FAILED_SAFE", decision.next_action, True,
                           False, decision.status, None, "ACTION_RESULT_INVALID")
        if (action_result.result_version != ACTION_RESULT_VERSION or
                action_result.action != decision.next_action or
                action_result.status not in
                {ACTION_SUCCEEDED, ACTION_FAILED, ACTION_UNCERTAIN}):
            return _result("ACTION_FAILED_SAFE", decision.next_action, True,
                           False, decision.status, None, "ACTION_RESULT_INVALID")
        if action_result.status == ACTION_UNCERTAIN:
            return _result("ACTION_UNCERTAIN", decision.next_action, True,
                           False, decision.status, None,
                           "ACTION_OUTCOME_UNCERTAIN")
        if action_result.status == ACTION_FAILED:
            return _result("ACTION_FAILED_SAFE", decision.next_action, True,
                           False, decision.status, None, "ACTION_REPORTED_FAILURE")

        if decision.next_action == "START_NEXT_GATE":
            if action_result.evidence is not None:
                return _result("ACTION_FAILED_SAFE", decision.next_action, True,
                               False, decision.status, None,
                               "START_RESULT_EVIDENCE_UNEXPECTED")
            return _result("NEXT_GATE_STARTED", decision.next_action, True,
                           True, decision.status, decision.status,
                           "NEXT_GATE_START_CONFIRMED")

        after = core.evaluate(action_result.evidence)
        if after.status not in _EXPECTED_AFTER.get(decision.next_action, frozenset()):
            return _result("ACTION_FAILED_SAFE", decision.next_action, True,
                           False, decision.status, after.status,
                           "ACTION_PROGRESS_INVALID")
        return _result("ACTION_COMPLETED", decision.next_action, True, False,
                       decision.status, after.status,
                       "ACTION_RESULT_REVALIDATED")


__all__ = [
    "ACTION_FAILED", "ACTION_RESULT_VERSION", "ACTION_SUCCEEDED",
    "ACTION_UNCERTAIN", "DevelopmentGateActionResult",
    "DevelopmentGateCoordinator", "DevelopmentGateCoordinatorResult",
]
