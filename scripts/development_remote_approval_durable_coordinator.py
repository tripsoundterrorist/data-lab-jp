"""Default-disabled durable coordinator for supplied remote approvals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import development_gate_coordinator as gate_coordinator
import development_gate_evidence as evidence_core
import development_remote_approval_replay_persistence as persistence_core
import development_remote_approval_replay_record as record_core
import development_remote_iphone_approval_observation as approval_core


COORDINATOR_VERSION = "0.1"
_TEST_TOKEN = object()


@dataclass(frozen=True)
class DurableRemoteApprovalResult:
    coordinator_version: str
    status: str
    evidence: evidence_core.DevelopmentGateEvidence | None
    durable: bool
    replay_blocked: bool
    reason_codes: tuple[str, ...]


Observer = Callable[..., gate_coordinator.DevelopmentGateActionResult]


def _result(status: str, *,
            evidence: evidence_core.DevelopmentGateEvidence | None = None,
            durable: bool = False, replay_blocked: bool = False,
            reasons: tuple[str, ...]) -> DurableRemoteApprovalResult:
    return DurableRemoteApprovalResult(
        COORDINATOR_VERSION, status, evidence, durable, replay_blocked,
        reasons,
    )


class DurableRemoteApprovalCoordinator:
    """Persist approval consumption before releasing approved evidence."""

    def __init__(
        self,
        store: persistence_core.RemoteApprovalReplayStore | None = None,
        observer: Observer = approval_core.observe,
        token: object | None = None,
    ):
        self._enabled = token is _TEST_TOKEN
        self._store = store if self._enabled else None
        self._observer = observer if self._enabled else None

    @classmethod
    def disabled(cls) -> "DurableRemoteApprovalCoordinator":
        return cls()

    @classmethod
    def _for_test(
        cls,
        store: persistence_core.RemoteApprovalReplayStore,
        observer: Observer = approval_core.observe,
    ) -> "DurableRemoteApprovalCoordinator":
        return cls(store, observer, _TEST_TOKEN)

    def coordinate(
        self,
        evidence: object,
        observation: object,
        *,
        evaluated_at_epoch_s: object,
        expected_revision: object,
    ) -> DurableRemoteApprovalResult:
        decision = evidence_core.evaluate(evidence)
        if decision.status != "APPROVAL_REQUIRED":
            return _result(
                "RECOVERY_BLOCKED",
                reasons=("REMOTE_APPROVAL_NOT_EXPECTED",),
            )
        if not self._enabled or self._store is None or self._observer is None:
            return _result(
                "AUTOMATION_DISABLED",
                reasons=("DURABLE_REMOTE_APPROVAL_AUTOMATION_DISABLED",),
            )
        if type(expected_revision) is not int or expected_revision < 0:
            return _result(
                "RECOVERY_BLOCKED",
                reasons=("REMOTE_APPROVAL_EXPECTED_REVISION_INVALID",),
            )

        try:
            loaded = self._store.load()
        except Exception:
            return _result(
                "REMOTE_APPROVAL_UNCERTAIN",
                reasons=("REMOTE_APPROVAL_REPLAY_LOAD_EXCEPTION",),
            )
        if (not isinstance(loaded, persistence_core.ReplayLoadResult) or
                loaded.status != "HEALTHY" or loaded.revision is None or
                loaded.records is None):
            reasons = getattr(
                loaded, "reason_codes",
                ("REMOTE_APPROVAL_REPLAY_LOAD_INVALID",),
            )
            return _result("RECOVERY_BLOCKED", reasons=tuple(reasons))
        if loaded.revision != expected_revision:
            return _result(
                "APPROVAL_CONFLICT",
                reasons=("STALE_REVISION",),
            )

        replay = record_core.find_consumed_request(
            list(loaded.records), getattr(observation, "request_id", None)
        )
        if replay.status.startswith("EVIDENCE_"):
            return _result("RECOVERY_BLOCKED", reasons=replay.reason_codes)
        if replay.consumed:
            return _result(
                "APPROVAL_REPLAY_BLOCKED", replay_blocked=True,
                reasons=replay.reason_codes,
            )

        try:
            action = self._observer(
                evidence, observation,
                evaluated_at_epoch_s=evaluated_at_epoch_s,
            )
        except Exception:
            return _result(
                "REMOTE_APPROVAL_UNCERTAIN",
                reasons=("REMOTE_APPROVAL_OBSERVER_EXCEPTION",),
            )
        if not isinstance(action, gate_coordinator.DevelopmentGateActionResult):
            return _result(
                "RECOVERY_BLOCKED",
                reasons=("REMOTE_APPROVAL_ACTION_RESULT_INVALID",),
            )
        if action.status == gate_coordinator.ACTION_UNCERTAIN:
            return _result(
                "REMOTE_APPROVAL_UNCERTAIN", reasons=action.reason_codes
            )
        if action.status != gate_coordinator.ACTION_SUCCEEDED:
            return _result("REMOTE_APPROVAL_REJECTED", reasons=action.reason_codes)

        record = record_core.build_record(observation, action)
        if record is None:
            return _result(
                "RECOVERY_BLOCKED",
                reasons=("REMOTE_APPROVAL_REPLAY_RECORD_INVALID",),
            )
        try:
            saved = self._store.save_record(record, expected_revision)
        except Exception:
            return _result(
                "REMOTE_APPROVAL_UNCERTAIN",
                reasons=("REMOTE_APPROVAL_REPLAY_SAVE_EXCEPTION",),
            )
        if not isinstance(saved, persistence_core.ReplaySaveResult):
            return _result(
                "REMOTE_APPROVAL_UNCERTAIN",
                reasons=("REMOTE_APPROVAL_REPLAY_SAVE_RESULT_INVALID",),
            )
        if saved.status == "SAVED":
            return _result(
                "REMOTE_APPROVAL_APPLIED_DURABLY", evidence=action.evidence,
                durable=True,
                reasons=("REMOTE_APPROVAL_RECORDED_DURABLY",),
            )
        if saved.status == "STALE_REVISION":
            return _result("APPROVAL_CONFLICT", reasons=saved.reason_codes)
        if saved.status == "ALREADY_CONSUMED":
            return _result(
                "APPROVAL_REPLAY_BLOCKED", replay_blocked=True,
                reasons=saved.reason_codes,
            )
        return _result("REMOTE_APPROVAL_UNCERTAIN", reasons=saved.reason_codes)


__all__ = [
    "COORDINATOR_VERSION", "DurableRemoteApprovalCoordinator",
    "DurableRemoteApprovalResult",
]
