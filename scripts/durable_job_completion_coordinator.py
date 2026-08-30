"""Durably complete one confirmed RUNNING generation without execution."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import unattended_job_queue as core
import unattended_queue_persistence as persistence


COORDINATOR_VERSION = "0.1"


@dataclass(frozen=True)
class DurableJobCompletionResult:
    coordinator_version: str
    status: str
    durable: bool
    job_id: str | None
    attempt_count: int | None
    revision: int | None
    reason_codes: tuple[str, ...]


def _result(status: str, reasons: tuple[str, ...], *, job_id: str | None = None,
            durable: bool = False,
            attempt_count: int | None = None,
            revision: int | None = None) -> DurableJobCompletionResult:
    return DurableJobCompletionResult(
        COORDINATOR_VERSION, status, durable, job_id, attempt_count, revision, reasons)


def _save_failure(saved: persistence.QueueSaveResult) -> DurableJobCompletionResult:
    if saved.status == "STALE_REVISION":
        return _result("COMPLETION_CONFLICT", ("STALE_REVISION",))
    if saved.status == "RECOVERY_BLOCKED" and any(
            code in {"QUEUE_READ_BACK_FAILED", "QUEUE_SAVE_FAILED"}
            for code in saved.reason_codes):
        return _result("JOB_COMPLETION_UNCERTAIN", ("RECOVERY_BLOCKED",))
    return _result("RECOVERY_BLOCKED", tuple(saved.reason_codes))


def complete_running_job_durably(
    store: Any, *, expected_job_id: Any, expected_attempt_count: Any,
) -> DurableJobCompletionResult:
    """Load, complete through Core, and accept Persistence's durable CAS result."""
    if not isinstance(store, persistence.QueuePersistenceStore):
        return _result("RECOVERY_BLOCKED", ("PERSISTENCE_STORE_INVALID",))
    if (type(expected_attempt_count) is not int or expected_attempt_count < 1):
        return _result("COMPLETION_REJECTED", ("EXECUTION_GENERATION_INVALID",))
    try:
        loaded = store.load_queue()
        if loaded.status != "HEALTHY" or loaded.snapshot is None:
            return _result("RECOVERY_BLOCKED", tuple(loaded.reason_codes))
        before = loaded.snapshot
        matches = [job for job in before.jobs if job.job_id == expected_job_id]
        if len(matches) != 1:
            return _result("COMPLETION_REJECTED", ("JOB_IDENTITY_NOT_CURRENT",))
        original = matches[0]
        if original.attempt_count != expected_attempt_count:
            return _result("COMPLETION_REJECTED", ("EXECUTION_GENERATION_MISMATCH",))
        candidate, transition = core.complete_job(
            original, expected_job_id=expected_job_id)
        validation = core.validate_job_transition_result(transition)
        if (candidate is None or not validation.valid
                or validation.transition_class != "COMPLETION_TRANSITION"
                or not core.validate_completion_transition(
                    original, candidate, expected_job_id=expected_job_id)):
            reason = (transition.reason_code
                      if candidate is None else "COMPLETION_TRANSITION_INVALID")
            return _result("COMPLETION_REJECTED", (reason,))
        jobs = tuple(candidate if job.job_id == expected_job_id else job
                     for job in before.jobs)
        proposed = replace(before, jobs=jobs)
        saved = store.save_queue(proposed, before.revision)
        if saved.status != "SAVED" or saved.revision != before.revision + 1:
            return _save_failure(saved)
        return _result("JOB_COMPLETED_DURABLY", ("JOB_COMPLETION_DURABLE",),
                       durable=True, job_id=candidate.job_id,
                       attempt_count=candidate.attempt_count,
                       revision=saved.revision)
    except Exception:
        return _result("RECOVERY_BLOCKED", ("COORDINATOR_INTERNAL_ERROR",))
