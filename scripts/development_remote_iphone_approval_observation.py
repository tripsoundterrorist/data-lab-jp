"""Pure observation adapter for supplied Codex Remote iPhone approval."""

from __future__ import annotations

from dataclasses import dataclass, replace
import re

import development_gate_coordinator as coordinator
import development_gate_evidence as evidence_core


OBSERVATION_VERSION = "0.1"
APPROVED_REPOSITORY = "tripsoundterrorist/data-lab-jp"
APPROVED_SOURCE = "CODEX_REMOTE"
APPROVED_DEVICE_CLASS = "IPHONE"
MAX_DECISION_AGE_SECONDS = 300
REQUEST_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")


@dataclass(frozen=True)
class RemoteApprovalObservation:
    observation_version: str
    source: str
    repository: str
    device_class: str
    request_id: str
    current_gate_id: str
    next_gate_id: str
    head_sha: str
    ci_run_id: int
    status: str
    requested_at_epoch_s: int
    decided_at_epoch_s: int | None


def _action(status: str, updated: evidence_core.DevelopmentGateEvidence | None,
            *reasons: str) -> coordinator.DevelopmentGateActionResult:
    return coordinator.DevelopmentGateActionResult(
        coordinator.ACTION_RESULT_VERSION, "REQUEST_APPROVAL", status,
        updated, tuple(reasons),
    )


def observe(evidence: object, observation: object, *,
            evaluated_at_epoch_s: object
            ) -> coordinator.DevelopmentGateActionResult:
    """Validate supplied observation; never contact Codex Remote or a device."""
    decision = evidence_core.evaluate(evidence)
    if decision.status != "APPROVAL_REQUIRED":
        return _action(
            coordinator.ACTION_FAILED, None, "REMOTE_APPROVAL_NOT_EXPECTED"
        )
    if not isinstance(observation, RemoteApprovalObservation):
        return _action(
            coordinator.ACTION_FAILED, None, "REMOTE_APPROVAL_INVALID"
        )
    if (observation.observation_version != OBSERVATION_VERSION or
            observation.source != APPROVED_SOURCE or
            observation.repository != APPROVED_REPOSITORY or
            observation.device_class != APPROVED_DEVICE_CLASS or
            type(observation.request_id) is not str or
            REQUEST_ID.fullmatch(observation.request_id) is None):
        return _action(
            coordinator.ACTION_FAILED, None,
            "REMOTE_APPROVAL_IDENTITY_INVALID",
        )
    if (observation.current_gate_id != evidence.current_gate_id or
            observation.next_gate_id != evidence.next_gate_id or
            observation.head_sha != evidence.commit_sha or
            observation.ci_run_id != evidence.ci_run_id):
        return _action(
            coordinator.ACTION_FAILED, None,
            "REMOTE_APPROVAL_TARGET_MISMATCH",
        )
    if (type(observation.requested_at_epoch_s) is not int or
            observation.requested_at_epoch_s < 0 or
            type(evaluated_at_epoch_s) is not int or
            evaluated_at_epoch_s < 0 or
            observation.requested_at_epoch_s > evaluated_at_epoch_s):
        return _action(
            coordinator.ACTION_FAILED, None,
            "REMOTE_APPROVAL_TIMESTAMP_INVALID",
        )
    if observation.status == "PENDING":
        if observation.decided_at_epoch_s is not None:
            return _action(
                coordinator.ACTION_FAILED, None,
                "REMOTE_APPROVAL_TIMESTAMP_INVALID",
            )
        return _action(
            coordinator.ACTION_UNCERTAIN, None, "REMOTE_APPROVAL_PENDING"
        )
    if observation.status not in {"APPROVED", "DENIED"}:
        return _action(
            coordinator.ACTION_FAILED, None, "REMOTE_APPROVAL_STATUS_INVALID"
        )
    if (type(observation.decided_at_epoch_s) is not int or
            observation.decided_at_epoch_s < observation.requested_at_epoch_s or
            observation.decided_at_epoch_s > evaluated_at_epoch_s):
        return _action(
            coordinator.ACTION_FAILED, None,
            "REMOTE_APPROVAL_TIMESTAMP_INVALID",
        )
    if evaluated_at_epoch_s - observation.decided_at_epoch_s > \
            MAX_DECISION_AGE_SECONDS:
        return _action(
            coordinator.ACTION_FAILED, None, "REMOTE_APPROVAL_STALE"
        )
    if observation.status == "DENIED":
        return _action(
            coordinator.ACTION_FAILED, None, "REMOTE_APPROVAL_DENIED"
        )

    updated = replace(evidence, approval_status="APPROVED")
    return _action(
        coordinator.ACTION_SUCCEEDED, updated,
        "REMOTE_IPHONE_APPROVAL_VALIDATED",
    )


__all__ = [
    "APPROVED_DEVICE_CLASS", "APPROVED_REPOSITORY", "APPROVED_SOURCE",
    "MAX_DECISION_AGE_SECONDS", "OBSERVATION_VERSION",
    "RemoteApprovalObservation", "observe",
]
