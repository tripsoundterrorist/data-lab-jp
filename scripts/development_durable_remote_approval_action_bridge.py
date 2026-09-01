"""Test-scoped bridge from durable approval results to Gate actions."""

from __future__ import annotations

import re

import development_gate_coordinator as gate_coordinator
import development_gate_evidence as evidence_core
import development_remote_approval_durable_coordinator as durable_core


BRIDGE_VERSION = "0.1"
_TEST_TOKEN = object()
_REASON = re.compile(r"[A-Z0-9_]+\Z")
_FAILED_STATUSES = frozenset({
    "RECOVERY_BLOCKED", "APPROVAL_CONFLICT", "APPROVAL_REPLAY_BLOCKED",
    "REMOTE_APPROVAL_REJECTED", "AUTOMATION_DISABLED",
})


def _action(
    status: str,
    evidence: evidence_core.DevelopmentGateEvidence | None,
    reasons: tuple[str, ...],
) -> gate_coordinator.DevelopmentGateActionResult:
    return gate_coordinator.DevelopmentGateActionResult(
        gate_coordinator.ACTION_RESULT_VERSION,
        "REQUEST_APPROVAL",
        status,
        evidence,
        reasons,
    )


def _valid_reasons(value: object) -> bool:
    return (
        type(value) is tuple and bool(value) and
        all(type(reason) is str and _REASON.fullmatch(reason) is not None
            for reason in value)
    )


class DurableRemoteApprovalActionBridge:
    """Expose approved evidence only for one exact durable result."""

    def __init__(
        self,
        coordinator: durable_core.DurableRemoteApprovalCoordinator | None = None,
        observation: object = None,
        *,
        evaluated_at_epoch_s: object = None,
        expected_revision: object = None,
        token: object | None = None,
    ):
        self._enabled = token is _TEST_TOKEN
        self._coordinator = coordinator if self._enabled else None
        self._observation = observation if self._enabled else None
        self._evaluated_at_epoch_s = (
            evaluated_at_epoch_s if self._enabled else None
        )
        self._expected_revision = expected_revision if self._enabled else None

    @classmethod
    def disabled(cls) -> "DurableRemoteApprovalActionBridge":
        return cls()

    @classmethod
    def _for_test(
        cls,
        coordinator: durable_core.DurableRemoteApprovalCoordinator,
        observation: object,
        *,
        evaluated_at_epoch_s: object,
        expected_revision: object,
    ) -> "DurableRemoteApprovalActionBridge":
        return cls(
            coordinator, observation,
            evaluated_at_epoch_s=evaluated_at_epoch_s,
            expected_revision=expected_revision,
            token=_TEST_TOKEN,
        )

    def __call__(self, evidence: object) -> gate_coordinator.DevelopmentGateActionResult:
        if not self._enabled or self._coordinator is None:
            return _action(
                gate_coordinator.ACTION_FAILED, None,
                ("DURABLE_REMOTE_APPROVAL_BRIDGE_DISABLED",),
            )
        try:
            result = self._coordinator.coordinate(
                evidence,
                self._observation,
                evaluated_at_epoch_s=self._evaluated_at_epoch_s,
                expected_revision=self._expected_revision,
            )
        except Exception:
            return _action(
                gate_coordinator.ACTION_UNCERTAIN, None,
                ("DURABLE_REMOTE_APPROVAL_COORDINATOR_EXCEPTION",),
            )

        if (not isinstance(result, durable_core.DurableRemoteApprovalResult) or
                result.coordinator_version != durable_core.COORDINATOR_VERSION or
                not _valid_reasons(result.reason_codes)):
            return _action(
                gate_coordinator.ACTION_FAILED, None,
                ("DURABLE_REMOTE_APPROVAL_RESULT_INVALID",),
            )
        if result.status == "REMOTE_APPROVAL_APPLIED_DURABLY":
            if (result.durable is not True or result.replay_blocked is not False or
                    evidence_core.evaluate(result.evidence).status !=
                    "NEXT_GATE_READY"):
                return _action(
                    gate_coordinator.ACTION_FAILED, None,
                    ("DURABLE_REMOTE_APPROVAL_RESULT_INVALID",),
                )
            return _action(
                gate_coordinator.ACTION_SUCCEEDED, result.evidence,
                ("DURABLE_REMOTE_APPROVAL_CONFIRMED",),
            )

        if (result.evidence is not None or result.durable is not False or
                result.replay_blocked is not
                (result.status == "APPROVAL_REPLAY_BLOCKED")):
            return _action(
                gate_coordinator.ACTION_FAILED, None,
                ("DURABLE_REMOTE_APPROVAL_RESULT_INVALID",),
            )
        if result.status == "REMOTE_APPROVAL_UNCERTAIN":
            return _action(
                gate_coordinator.ACTION_UNCERTAIN, None, result.reason_codes
            )
        if result.status in _FAILED_STATUSES:
            return _action(
                gate_coordinator.ACTION_FAILED, None, result.reason_codes
            )
        return _action(
            gate_coordinator.ACTION_FAILED, None,
            ("DURABLE_REMOTE_APPROVAL_RESULT_INVALID",),
        )


__all__ = ["BRIDGE_VERSION", "DurableRemoteApprovalActionBridge"]
