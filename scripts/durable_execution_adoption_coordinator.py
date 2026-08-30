"""Durably adopt one selected READY job without invoking an executor."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

import unattended_job_queue as core
import unattended_queue_persistence as persistence


COORDINATOR_VERSION = "0.1"


@dataclass(frozen=True)
class DurableExecutionAdoptionResult:
    coordinator_version: str
    status: str
    job_id: str | None
    attempt_count: int | None
    revision: int | None
    reason_codes: tuple[str, ...]


def _result(status: str, reasons: tuple[str, ...], *, job_id: str | None = None,
            attempt_count: int | None = None,
            revision: int | None = None) -> DurableExecutionAdoptionResult:
    return DurableExecutionAdoptionResult(
        COORDINATOR_VERSION, status, job_id, attempt_count, revision, reasons)


def adopt_selected_job_durably(
    store: Any, *, expected_job_id: Any, occurred_at: Any,
    window_states: Mapping[str, str] | None = None,
    external_read_allowed: bool = False,
) -> DurableExecutionAdoptionResult:
    """Load, adopt through Core, CAS-save, and confirm the stored generation.

    The coordinator never executes a job and never retries a failed or uncertain
    persistence operation. Any ambiguity fails closed for operator inspection.
    """
    if not isinstance(store, persistence.QueuePersistenceStore):
        return _result("RECOVERY_BLOCKED", ("PERSISTENCE_STORE_INVALID",))
    try:
        loaded = store.load_queue()
        if loaded.status != "HEALTHY" or loaded.snapshot is None:
            return _result("RECOVERY_BLOCKED", tuple(loaded.reason_codes))
        before = loaded.snapshot
        candidate, transition = core.adopt_ready_job_for_execution(
            before.jobs, expected_job_id=expected_job_id, occurred_at=occurred_at,
            window_states=window_states, external_read_allowed=external_read_allowed)
        if candidate is None:
            return _result("ADOPTION_REJECTED", (transition.reason_code,))
        originals = {job.job_id: job for job in before.jobs}
        original = originals.get(expected_job_id)
        if original is None or not core.validate_execution_adoption_transition(
                original, candidate, transition, expected_job_id=expected_job_id):
            return _result("RECOVERY_BLOCKED", ("ADOPTION_TRANSITION_INVALID",))
        jobs = tuple(candidate if job.job_id == expected_job_id else job
                     for job in before.jobs)
        proposed = replace(before, jobs=jobs)
        saved = store.save_queue(proposed, before.revision)
        if saved.status != "SAVED" or saved.revision != before.revision + 1:
            return _result("PERSISTENCE_NOT_CONFIRMED", tuple(saved.reason_codes))
        confirmed = store.load_queue()
        if confirmed.status != "HEALTHY" or confirmed.snapshot is None:
            return _result("PERSISTENCE_NOT_CONFIRMED", ("QUEUE_CONFIRMATION_FAILED",))
        expected = replace(proposed, revision=saved.revision)
        if confirmed.snapshot != expected:
            return _result("PERSISTENCE_NOT_CONFIRMED", ("QUEUE_CONFIRMATION_MISMATCH",))
        stored = next((job for job in confirmed.snapshot.jobs
                       if job.job_id == expected_job_id), None)
        if stored != candidate:
            return _result("PERSISTENCE_NOT_CONFIRMED", ("GENERATION_CONFIRMATION_MISMATCH",))
        return _result("ADOPTED", ("EXECUTION_ADOPTION_DURABLE",),
                       job_id=stored.job_id, attempt_count=stored.attempt_count,
                       revision=confirmed.snapshot.revision)
    except Exception:
        return _result("RECOVERY_BLOCKED", ("COORDINATOR_INTERNAL_ERROR",))
