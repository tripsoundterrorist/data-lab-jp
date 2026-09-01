"""Mock-only end-to-end integration for durable remote approvals."""

from __future__ import annotations

from dataclasses import dataclass

import development_durable_remote_approval_action_bridge as bridge_core
import development_gate_coordinator as gate_core
import development_remote_approval_durable_coordinator as durable_core
import development_remote_approval_replay_persistence as persistence_core


INTEGRATION_VERSION = "0.1"
_TEST_TOKEN = object()


@dataclass(frozen=True)
class RemoteApprovalE2EMockResult:
    integration_version: str
    status: str
    approval_action_invoked: bool
    next_gate_ready: bool
    next_gate_started: bool
    reason_codes: tuple[str, ...]


def _result(
    status: str,
    *,
    invoked: bool = False,
    ready: bool = False,
    reasons: tuple[str, ...],
) -> RemoteApprovalE2EMockResult:
    return RemoteApprovalE2EMockResult(
        INTEGRATION_VERSION, status, invoked, ready, False, reasons
    )


class RemoteApprovalE2EMockIntegration:
    """Join the existing approval path without production activation."""

    def __init__(
        self,
        store: persistence_core.RemoteApprovalReplayStore | None = None,
        token: object | None = None,
    ):
        self._enabled = token is _TEST_TOKEN
        self._store = store if self._enabled else None

    @classmethod
    def disabled(cls) -> "RemoteApprovalE2EMockIntegration":
        return cls()

    @classmethod
    def _for_test(
        cls,
        store: persistence_core.RemoteApprovalReplayStore,
    ) -> "RemoteApprovalE2EMockIntegration":
        return cls(store, _TEST_TOKEN)

    def run(
        self,
        evidence: object,
        observation: object,
        *,
        evaluated_at_epoch_s: object,
        expected_revision: object,
    ) -> RemoteApprovalE2EMockResult:
        if not self._enabled or self._store is None:
            return _result(
                "AUTOMATION_DISABLED",
                reasons=("REMOTE_APPROVAL_E2E_MOCK_DISABLED",),
            )
        try:
            durable = durable_core.DurableRemoteApprovalCoordinator._for_test(
                self._store
            )
            bridge = bridge_core.DurableRemoteApprovalActionBridge._for_test(
                durable,
                observation,
                evaluated_at_epoch_s=evaluated_at_epoch_s,
                expected_revision=expected_revision,
            )
            coordinated = gate_core.DevelopmentGateCoordinator._for_test({
                "REQUEST_APPROVAL": bridge,
            }).coordinate(evidence)
        except Exception:
            return _result(
                "MOCK_APPROVAL_FLOW_UNCERTAIN",
                reasons=("REMOTE_APPROVAL_E2E_MOCK_EXCEPTION",),
            )

        if not isinstance(coordinated, gate_core.DevelopmentGateCoordinatorResult):
            return _result(
                "MOCK_APPROVAL_FLOW_BLOCKED",
                reasons=("REMOTE_APPROVAL_E2E_RESULT_INVALID",),
            )
        if (coordinated.status == "ACTION_COMPLETED" and
                coordinated.planned_action == "REQUEST_APPROVAL" and
                coordinated.action_invoked is True and
                coordinated.next_gate_started is False and
                coordinated.before_status == "APPROVAL_REQUIRED" and
                coordinated.after_status == "NEXT_GATE_READY"):
            return _result(
                "MOCK_APPROVAL_FLOW_COMPLETED", invoked=True, ready=True,
                reasons=("REMOTE_APPROVAL_E2E_DURABLE_SUCCESS",),
            )
        if coordinated.status == "ACTION_UNCERTAIN":
            return _result(
                "MOCK_APPROVAL_FLOW_UNCERTAIN",
                invoked=coordinated.action_invoked is True,
                reasons=("REMOTE_APPROVAL_E2E_OUTCOME_UNCERTAIN",),
            )
        return _result(
            "MOCK_APPROVAL_FLOW_BLOCKED",
            invoked=coordinated.action_invoked is True,
            reasons=("REMOTE_APPROVAL_E2E_FAIL_CLOSED",),
        )


__all__ = [
    "INTEGRATION_VERSION", "RemoteApprovalE2EMockIntegration",
    "RemoteApprovalE2EMockResult",
]
