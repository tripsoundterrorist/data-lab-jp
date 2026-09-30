"""Temporary-store coordinator for durable fresh execution adoption.

The coordinator composes existing Core and Queue Persistence contracts. It
does not execute jobs, dispatch notifications, create checkpoints, retry,
recover RUNNING jobs, or enable production writes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

import unattended_job_queue as core
import unattended_queue_persistence as persistence


ADOPTION_VERSION = "0.1"
_UNCERTAIN_REASONS = frozenset({"QUEUE_READ_BACK_FAILED", "QUEUE_SAVE_FAILED"})


@dataclass(frozen=True)
class ExecutionAdoptionResult:
    adoption_version: str
    status: str
    job_id: str | None
    previous_revision: int | None
    resulting_revision: int | None
    previous_attempt_count: int | None
    resulting_attempt_count: int | None
    transition_class: str
    durable: bool
    action_required: str
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **{key: value for key, value in self.__dict__.items()
               if key != "reason_codes"},
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class DurableExecutionReceipt:
    running_job: core.JobContract
    resulting_revision: int
    transition_result: core.JobTransitionResult
    generation: tuple[str, int]


def _result(
    status: str, *, job_id: str | None = None,
    previous_revision: int | None = None,
    resulting_revision: int | None = None,
    previous_attempt_count: int | None = None,
    resulting_attempt_count: int | None = None,
    transition_class: str = "NONE", durable: bool = False,
    action_required: str = "STOP", reason_codes: tuple[str, ...],
) -> ExecutionAdoptionResult:
    return ExecutionAdoptionResult(
        ADOPTION_VERSION, status, job_id, previous_revision,
        resulting_revision, previous_attempt_count, resulting_attempt_count,
        transition_class, durable, action_required, reason_codes)


def replace_job_in_snapshot(
    snapshot: Any, candidate: Any,
) -> persistence.PersistedQueueSnapshot | None:
    """Pure same-index replacement; revision, identity, order and refs remain."""
    try:
        if (not persistence.validate_snapshot(snapshot)[0]
                or type(candidate) is not core.JobContract):
            return None
        indexes = [index for index, job in enumerate(snapshot.jobs)
                   if job.job_id == candidate.job_id]
        if len(indexes) != 1:
            return None
        jobs = list(snapshot.jobs)
        jobs[indexes[0]] = candidate
        updated = replace(snapshot, jobs=tuple(jobs))
        return updated if persistence.validate_snapshot(updated)[0] else None
    except Exception:
        return None


def adopt_job_durably(
    store: persistence.QueuePersistenceStore, *, expected_job_id: Any,
    occurred_at: Any, window_states: Mapping[str, str] | None = None,
    external_read_allowed: bool = False,
) -> tuple[DurableExecutionReceipt | None, ExecutionAdoptionResult]:
    """Acquire durable fresh RUNNING ownership in an explicit test-backed store.

    A successful QueueSaveResult is already read back by Persistence. This
    function deliberately performs no second load after save.
    """
    invalid = _result("ADOPTION_BLOCKED", reason_codes=("ADOPTION_INPUT_INVALID",))
    try:
        if not isinstance(store, persistence.QueuePersistenceStore):
            return None, invalid
        loaded = store.load_queue(validate_active_objects=True)
        if loaded.status != "HEALTHY" or loaded.snapshot is None:
            action = ("RECOVERY_REQUIRED" if loaded.status in
                      {"RECOVERY_BLOCKED", "MANUAL_REVIEW_REQUIRED"}
                      else "STOP")
            return None, _result(
                loaded.status, action_required=action,
                reason_codes=loaded.reason_codes)
        snapshot = loaded.snapshot
        if not persistence.validate_snapshot(snapshot)[0]:
            return None, _result(
                "RECOVERY_BLOCKED", previous_revision=snapshot.revision,
                action_required="RECOVERY_REQUIRED",
                reason_codes=("PERSISTED_SNAPSHOT_INVALID",))
        target = next((job for job in snapshot.jobs
                       if job.job_id == expected_job_id), None)
        safe_job_id = target.job_id if target is not None else None
        previous_attempt = target.attempt_count if target is not None else None
        common = {
            "job_id": safe_job_id,
            "previous_revision": snapshot.revision,
            "previous_attempt_count": previous_attempt,
        }
        if any(ref.job_id == expected_job_id
               for ref in snapshot.active_checkpoint_refs):
            return None, _result(
                "ADOPTION_BLOCKED", **common,
                reason_codes=("FRESH_ROUTE_CHECKPOINT_REFERENCE_PRESENT",))

        candidate, transition = core.adopt_ready_job_for_execution(
            snapshot.jobs, expected_job_id=expected_job_id,
            occurred_at=occurred_at, window_states=window_states,
            external_read_allowed=external_read_allowed)
        if candidate is None or target is None:
            return None, _result(
                "ADOPTION_REJECTED", **common,
                action_required="NONE", reason_codes=(transition.reason_code,))
        transition_validation = core.validate_job_transition_result(transition)
        if (not core.validate_execution_adoption_transition(
                target, candidate, transition,
                expected_job_id=expected_job_id)
                or not transition_validation.valid
                or transition_validation.transition_class !=
                "EXECUTION_ADOPTION_TRANSITION"):
            return None, _result(
                "ADOPTION_BLOCKED", **common,
                action_required="MANUAL_REVIEW",
                reason_codes=("CORE_TRANSITION_VALIDATION_FAILED",))
        updated = replace_job_in_snapshot(snapshot, candidate)
        if updated is None:
            return None, _result(
                "ADOPTION_BLOCKED", **common,
                action_required="MANUAL_REVIEW",
                reason_codes=("UPDATED_SNAPSHOT_INVALID",))

        saved = store.save_queue(updated, expected_revision=snapshot.revision)
        if (saved.status == "SAVED"
                and saved.revision == snapshot.revision + 1):
            result = _result(
                "EXECUTION_ADOPTED_DURABLY", **common,
                resulting_revision=saved.revision,
                resulting_attempt_count=candidate.attempt_count,
                transition_class=transition_validation.transition_class,
                durable=True, action_required="NONE",
                reason_codes=("EXECUTION_ADOPTED_DURABLY",))
            receipt = DurableExecutionReceipt(
                candidate, saved.revision, transition,
                (candidate.job_id, candidate.attempt_count))
            return receipt, result
        if saved.status == "STALE_REVISION":
            return None, _result(
                "ADOPTION_CONFLICT", **common,
                action_required="RELOAD_AND_RESELECT",
                reason_codes=("STALE_REVISION",))
        if (saved.status == "SAVED"
                or any(code in _UNCERTAIN_REASONS
                       for code in saved.reason_codes)):
            return None, _result(
                "EXECUTION_ADOPTION_UNCERTAIN", **common,
                action_required="RECOVERY_REQUIRED",
                reason_codes=tuple(sorted(set(saved.reason_codes)
                                          | {"RECOVERY_BLOCKED"})))
        action = ("RECOVERY_REQUIRED" if saved.status in
                  {"RECOVERY_BLOCKED", "MANUAL_REVIEW_REQUIRED"}
                  else "STOP")
        return None, _result(
            saved.status, **common, action_required=action,
            reason_codes=saved.reason_codes)
    except Exception:
        return None, _result(
            "ADOPTION_BLOCKED", action_required="MANUAL_REVIEW",
            reason_codes=("COORDINATOR_INTERNAL_ERROR",))


__all__ = [
    "ADOPTION_VERSION", "DurableExecutionReceipt", "ExecutionAdoptionResult",
    "adopt_job_durably", "replace_job_in_snapshot",
]
