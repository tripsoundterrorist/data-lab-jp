"""Pure observation adapter for an already-completed checkpoint save."""

from __future__ import annotations

from dataclasses import replace

import development_gate_coordinator as coordinator
import development_gate_evidence as evidence_core
import unattended_checkpoint_storage as checkpoint_storage


OBSERVATION_VERSION = "0.1"
_EXPECTED_REASONS = {
    "SAVED": ("CHECKPOINT_STORED",),
    "NO_CHANGE": ("CHECKPOINT_ALREADY_STORED",),
}


def _action(
    status: str,
    evidence: evidence_core.DevelopmentGateEvidence | None,
    *reasons: str,
) -> coordinator.DevelopmentGateActionResult:
    return coordinator.DevelopmentGateActionResult(
        coordinator.ACTION_RESULT_VERSION,
        "SAVE_CHECKPOINT",
        status,
        evidence,
        tuple(reasons),
    )


def observe(
    evidence: object,
    result: object,
) -> coordinator.DevelopmentGateActionResult:
    """Validate supplied durable evidence; never save, load, retry, or write."""
    decision = evidence_core.evaluate(evidence)
    if decision.status != "CHECKPOINT_REQUIRED":
        return _action(
            coordinator.ACTION_FAILED, None,
            "CHECKPOINT_OBSERVATION_NOT_EXPECTED",
        )
    if type(result) is not checkpoint_storage.CheckpointSaveResult:
        return _action(
            coordinator.ACTION_FAILED, None,
            "CHECKPOINT_SAVE_RESULT_INVALID",
        )
    if (result.result_version != checkpoint_storage.CHECKPOINT_RESULT_VERSION or
            result.status not in evidence_core.DURABLE_CHECKPOINT_STATUSES or
            type(result.checkpoint_storage_id) is not str or
            evidence_core.CHECKPOINT_REF.fullmatch(
                result.checkpoint_storage_id
            ) is None or
            result.reason_codes != _EXPECTED_REASONS[result.status]):
        return _action(
            coordinator.ACTION_FAILED, None,
            "CHECKPOINT_SAVE_RESULT_INVALID",
        )
    assert isinstance(evidence, evidence_core.DevelopmentGateEvidence)
    updated = replace(
        evidence,
        checkpoint_status=result.status,
        checkpoint_ref=result.checkpoint_storage_id,
    )
    return _action(
        coordinator.ACTION_SUCCEEDED, updated,
        "CHECKPOINT_SAVE_RESULT_VALIDATED",
    )


__all__ = ["OBSERVATION_VERSION", "observe"]
