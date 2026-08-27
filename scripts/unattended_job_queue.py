"""Pure fail-closed scheduling policy for unattended local jobs.

The module performs no process execution, persistence, network access, approval,
notification delivery, or environment mutation.  Callers provide sanitized
contracts and explicit fixture/preflight facts and receive bounded decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import re
from typing import Any, Mapping, Sequence


QUEUE_VERSION = "0.1"
EVENT_VERSION = "0.1"
TRANSITION_VERSION = "0.1"
COMPLETION_CONTRACT_VERSION = "0.1"
FAILED_SAFE_CONTRACT_VERSION = "0.1"

READY = "READY"
RUNNING = "RUNNING"
WAITING_APPROVAL = "WAITING_APPROVAL"
BLOCKED = "BLOCKED"
RETRY_WAIT = "RETRY_WAIT"
FAILED_SAFE = "FAILED_SAFE"
CHECKPOINTED = "CHECKPOINTED"
DONE = "DONE"
CANCELLED = "CANCELLED"
JOB_STATES = frozenset({
    READY, RUNNING, WAITING_APPROVAL, BLOCKED, RETRY_WAIT, FAILED_SAFE,
    CHECKPOINTED, DONE, CANCELLED,
})

READ_ONLY = "READ_ONLY"
LOW_RISK_LOCAL = "LOW_RISK_LOCAL"
EXTERNAL_READ = "EXTERNAL_READ"
APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
PROHIBITED_UNATTENDED = "PROHIBITED_UNATTENDED"
RISK_CLASSES = frozenset({
    READ_ONLY, LOW_RISK_LOCAL, EXTERNAL_READ, APPROVAL_REQUIRED,
    PROHIBITED_UNATTENDED,
})

PRIORITIES = frozenset({"P0", "P1", "P2", "P3"})
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
DEADLINE_CLASSES = frozenset({"NONE", "SOFT", "TIME_WINDOW", "HARD"})
RETRY_POLICIES = frozenset({"NONE", "TRANSIENT_ONLY", "EXPLICIT_LOCAL"})
WINDOW_STATES = frozenset({"OPEN", "CLOSED", "EXPIRED"})

EVENT_TYPES = frozenset({
    "JOB_STARTED", "JOB_COMPLETED", "JOB_FAILED_SAFE",
    "JOB_WAITING_APPROVAL", "JOB_CHECKPOINTED", "JOB_SWITCHED",
    "QUEUE_IDLE", "QUEUE_BLOCKED", "CRITICAL_STOP",
})
SEVERITIES = frozenset({"INFO", "WARN", "ERROR", "CRITICAL"})
SAFE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
SAFE_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
URL = re.compile(r"(?i)(?:https?|ftp|file)://|www\.")
ABSOLUTE_PATH = re.compile(r"(?i)(?:[a-z]:[\\/]|^/|^\\\\)")
FORBIDDEN_NAMES = re.compile(
    r"(?i)(?:api|affiliate)[_-]?id|credential|password|secret|token|"
    r"raw(?:_response|_exception)?|traceback|title|url|content_ids?|product_ids?|path"
)


@dataclass(frozen=True)
class JobContract:
    queue_version: str
    job_id: str
    job_type: str
    priority: str
    risk_class: str
    dependencies: tuple[str, ...]
    blocker_codes: tuple[str, ...]
    requires_approval: bool
    retry_policy: str
    max_attempts: int
    checkpoint_supported: bool
    created_at: str
    deadline_class: str
    state: str = READY
    attempt_count: int = 0
    approval_received: bool = False


@dataclass(frozen=True)
class QueueDecision:
    queue_version: str
    status: str
    selected_job_id: str | None
    action: str
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "reason_codes": list(self.reason_codes)}


@dataclass(frozen=True)
class Checkpoint:
    job_id: str
    state: str
    last_completed_step: str
    resume_preconditions: tuple[str, ...]
    blocker_codes: tuple[str, ...]
    attempt_count: int
    checkpoint_time: str
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **{key: value for key, value in self.__dict__.items() if key not in {"resume_preconditions", "blocker_codes", "reason_codes"}},
            "resume_preconditions": list(self.resume_preconditions),
            "blocker_codes": list(self.blocker_codes),
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class ResumeDecision:
    status: str
    resume_allowed: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class RetryDecision:
    state: str
    retry_allowed: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class NotificationEvent:
    event_version: str
    event_type: str
    job_id: str
    job_type: str
    severity: str
    state: str
    approval_required: bool
    summary_code: str
    occurred_at: str

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None


def _codes(value: Any, *, empty: bool = True) -> bool:
    return (
        isinstance(value, tuple)
        and (empty or bool(value))
        and len(value) == len(set(value))
        and all(isinstance(code, str) and SAFE_CODE.fullmatch(code) for code in value)
    )


def _safe_text(value: Any, pattern: re.Pattern[str] = SAFE_TOKEN) -> bool:
    return (
        isinstance(value, str) and pattern.fullmatch(value) is not None
        and FORBIDDEN_NAMES.search(value) is None
        and URL.search(value) is None and ABSOLUTE_PATH.search(value) is None
    )


def validate_job(job: Any) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    if not isinstance(job, JobContract):
        return False, ("JOB_CONTRACT_INVALID",)
    if job.queue_version != QUEUE_VERSION:
        reasons.append("QUEUE_VERSION_UNSUPPORTED")
    if not _safe_text(job.job_id) or not _safe_text(job.job_type):
        reasons.append("JOB_IDENTITY_INVALID")
    if job.state not in JOB_STATES:
        reasons.append("JOB_STATE_UNKNOWN")
    if job.risk_class not in RISK_CLASSES:
        reasons.append("RISK_CLASS_UNKNOWN")
    if job.priority not in PRIORITIES:
        reasons.append("PRIORITY_UNKNOWN")
    if job.deadline_class not in DEADLINE_CLASSES:
        reasons.append("DEADLINE_CLASS_UNKNOWN")
    if job.retry_policy not in RETRY_POLICIES:
        reasons.append("RETRY_POLICY_UNKNOWN")
    if (
        not isinstance(job.dependencies, tuple)
        or len(job.dependencies) != len(set(job.dependencies))
        or any(not _safe_text(value) for value in job.dependencies)
        or job.job_id in job.dependencies
    ):
        reasons.append("DEPENDENCY_INVALID")
    if not _codes(job.blocker_codes):
        reasons.append("BLOCKER_CODES_INVALID")
    if not isinstance(job.requires_approval, bool) or not isinstance(job.checkpoint_supported, bool) or not isinstance(job.approval_received, bool):
        reasons.append("BOOLEAN_FLAG_INVALID")
    if not isinstance(job.max_attempts, int) or isinstance(job.max_attempts, bool) or job.max_attempts < 1:
        reasons.append("MAX_ATTEMPTS_INVALID")
    if not isinstance(job.attempt_count, int) or isinstance(job.attempt_count, bool) or job.attempt_count < 0:
        reasons.append("ATTEMPT_COUNT_INVALID")
    elif isinstance(job.max_attempts, int) and job.attempt_count > job.max_attempts:
        reasons.append("MAX_ATTEMPTS_EXCEEDED")
    if _time(job.created_at) is None:
        reasons.append("CREATED_AT_INVALID")
    if job.state == RUNNING and job.requires_approval and not job.approval_received:
        reasons.append("APPROVAL_REQUIRED_WHILE_RUNNING")
    if job.state == READY and job.risk_class == PROHIBITED_UNATTENDED:
        reasons.append("PROHIBITED_JOB_READY")
    if job.approval_received and not job.requires_approval:
        reasons.append("APPROVAL_FLAGS_CONTRADICTORY")
    if job.state == RETRY_WAIT and job.retry_policy == "NONE":
        reasons.append("RETRY_FLAGS_CONTRADICTORY")
    if job.state == CHECKPOINTED and not job.checkpoint_supported:
        reasons.append("CHECKPOINT_FLAGS_CONTRADICTORY")
    return not reasons, tuple(sorted(set(reasons)))


def _cycle(jobs: Mapping[str, JobContract]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(job_id: str) -> bool:
        if job_id in visiting:
            return True
        if job_id in visited:
            return False
        visiting.add(job_id)
        for dependency in jobs[job_id].dependencies:
            if dependency in jobs and visit(dependency):
                return True
        visiting.remove(job_id)
        visited.add(job_id)
        return False
    return any(visit(job_id) for job_id in jobs)


def validate_queue(jobs: Any) -> tuple[bool, tuple[str, ...]]:
    if not isinstance(jobs, (list, tuple)):
        return False, ("QUEUE_CONTRACT_INVALID",)
    if any(not isinstance(job, JobContract) for job in jobs):
        return False, ("JOB_CONTRACT_INVALID",)
    ids = [job.job_id for job in jobs]
    reasons: list[str] = []
    if len(ids) != len(set(ids)):
        reasons.append("DUPLICATE_JOB_ID")
    mapping = {job.job_id: job for job in jobs}
    for job in jobs:
        valid, job_reasons = validate_job(job)
        if not valid:
            reasons.extend(job_reasons)
        if any(dependency not in mapping for dependency in job.dependencies):
            reasons.append("DEPENDENCY_UNKNOWN")
    if len(mapping) == len(jobs) and _cycle(mapping):
        reasons.extend(("DEPENDENCY_CYCLE", "MANUAL_REVIEW_REQUIRED"))
    return not reasons, tuple(sorted(set(reasons)))


def _window_allows(job: JobContract, window_states: Mapping[str, str]) -> bool:
    if job.deadline_class not in {"TIME_WINDOW", "HARD"}:
        return True
    return window_states.get(job.job_id) == "OPEN"


def _risk_allows(job: JobContract, external_read_allowed: bool) -> bool:
    if job.risk_class in {READ_ONLY, LOW_RISK_LOCAL}:
        return True
    if job.risk_class == EXTERNAL_READ:
        return external_read_allowed
    if job.risk_class == APPROVAL_REQUIRED:
        return job.requires_approval and job.approval_received
    return False


def select_next_job(
    jobs: Any, *, window_states: Mapping[str, str] | None = None,
    external_read_allowed: bool = False,
) -> QueueDecision:
    try:
        valid, reasons = validate_queue(jobs)
        if not valid:
            return QueueDecision(QUEUE_VERSION, "QUEUE_BLOCKED", None, "QUEUE_BLOCKED", reasons)
        if window_states is None:
            window_states = {}
        if not isinstance(window_states, Mapping) or any(value not in WINDOW_STATES for value in window_states.values()):
            return QueueDecision(QUEUE_VERSION, "QUEUE_BLOCKED", None, "QUEUE_BLOCKED", ("WINDOW_STATE_INVALID",))
        mapping = {job.job_id: job for job in jobs}
        eligible = [
            job for job in jobs
            if job.state == READY
            and all(mapping[dependency].state == DONE for dependency in job.dependencies)
            and not job.blocker_codes
            and _risk_allows(job, external_read_allowed)
            and (not job.requires_approval or job.approval_received)
            and job.attempt_count < job.max_attempts
            and _window_allows(job, window_states)
        ]
        if not eligible:
            return QueueDecision(QUEUE_VERSION, "QUEUE_IDLE", None, "QUEUE_IDLE", ("NO_ELIGIBLE_JOB",))
        selected = min(eligible, key=lambda job: (PRIORITY_ORDER[job.priority], job.created_at, job.job_id))
        return QueueDecision(QUEUE_VERSION, "JOB_SELECTED", selected.job_id, "START_JOB", ("READY_JOB_SELECTED",))
    except Exception:
        return QueueDecision(QUEUE_VERSION, "QUEUE_BLOCKED", None, "CRITICAL_STOP", ("INTERNAL_QUEUE_ERROR",))


def switch_after_pause(current_job_id: Any, jobs: Any, **kwargs: Any) -> QueueDecision:
    try:
        valid, reasons = validate_queue(jobs)
        mapping = {job.job_id: job for job in jobs} if isinstance(jobs, (list, tuple)) else {}
        if not valid or current_job_id not in mapping:
            return QueueDecision(QUEUE_VERSION, "QUEUE_BLOCKED", None, "QUEUE_BLOCKED", reasons or ("CURRENT_JOB_UNKNOWN",))
        if mapping[current_job_id].state not in {WAITING_APPROVAL, BLOCKED, RETRY_WAIT, CHECKPOINTED, FAILED_SAFE}:
            return QueueDecision(QUEUE_VERSION, "QUEUE_BLOCKED", None, "QUEUE_BLOCKED", ("CURRENT_JOB_NOT_SWITCHABLE",))
        decision = select_next_job(jobs, **kwargs)
        if decision.selected_job_id is None:
            return decision
        return replace(decision, action="SWITCH_TO_NEXT_JOB", reason_codes=("SWITCH_TO_NEXT_JOB",))
    except Exception:
        return QueueDecision(QUEUE_VERSION, "QUEUE_BLOCKED", None, "CRITICAL_STOP", ("INTERNAL_QUEUE_ERROR",))


def create_checkpoint(
    job: JobContract, *, last_completed_step: str,
    resume_preconditions: Sequence[str], checkpoint_time: str,
    reason_codes: Sequence[str],
) -> Checkpoint | None:
    try:
        if not validate_job(job)[0] or not job.checkpoint_supported:
            return None
        checkpoint = Checkpoint(
            job.job_id, CHECKPOINTED, last_completed_step,
            tuple(resume_preconditions), job.blocker_codes, job.attempt_count,
            checkpoint_time, tuple(reason_codes),
        )
        return checkpoint if validate_checkpoint(checkpoint)[0] else None
    except Exception:
        return None


def validate_checkpoint(checkpoint: Any) -> tuple[bool, tuple[str, ...]]:
    if not isinstance(checkpoint, Checkpoint):
        return False, ("CHECKPOINT_INVALID",)
    reasons: list[str] = []
    if not _safe_text(checkpoint.job_id) or not _safe_text(checkpoint.last_completed_step):
        reasons.append("CHECKPOINT_METADATA_INVALID")
    if checkpoint.state != CHECKPOINTED:
        reasons.append("CHECKPOINT_STATE_INVALID")
    if not _codes(checkpoint.resume_preconditions) or not _codes(checkpoint.blocker_codes) or not _codes(checkpoint.reason_codes, empty=False):
        reasons.append("CHECKPOINT_CODES_INVALID")
    if not isinstance(checkpoint.attempt_count, int) or isinstance(checkpoint.attempt_count, bool) or checkpoint.attempt_count < 0:
        reasons.append("CHECKPOINT_ATTEMPT_INVALID")
    if _time(checkpoint.checkpoint_time) is None:
        reasons.append("CHECKPOINT_TIME_INVALID")
    if any(FORBIDDEN_NAMES.search(str(value)) or URL.search(str(value)) or ABSOLUTE_PATH.search(str(value)) for value in checkpoint.__dict__.values()):
        reasons.append("CHECKPOINT_UNSAFE")
    return not reasons, tuple(sorted(set(reasons)))


def resume_from_checkpoint(
    job: JobContract, checkpoint: Any, *, now: str,
    dependency_states: Mapping[str, str], environment_preflight_passed: bool,
    checkpoint_max_age_seconds: int = 86400,
) -> ResumeDecision:
    try:
        valid, reasons = validate_checkpoint(checkpoint)
        if not valid or not validate_job(job)[0] or checkpoint.job_id != job.job_id:
            return ResumeDecision(FAILED_SAFE, False, reasons or ("JOB_CHECKPOINT_MISMATCH",))
        if job.state != CHECKPOINTED:
            return ResumeDecision(FAILED_SAFE, False, ("JOB_NOT_CHECKPOINTED",))
        current = _time(now); saved = _time(checkpoint.checkpoint_time)
        if current is None or saved is None or current < saved or (current - saved).total_seconds() > checkpoint_max_age_seconds:
            return ResumeDecision(FAILED_SAFE, False, ("CHECKPOINT_STALE",))
        if not isinstance(environment_preflight_passed, bool) or not environment_preflight_passed:
            return ResumeDecision(BLOCKED, False, ("ENVIRONMENT_PREFLIGHT_REQUIRED",))
        if any(dependency_states.get(value) != DONE for value in job.dependencies):
            return ResumeDecision(BLOCKED, False, ("DEPENDENCY_NOT_DONE",))
        blockers = set(job.blocker_codes) | set(checkpoint.blocker_codes)
        if blockers:
            return ResumeDecision(BLOCKED, False, ("BLOCKER_PRESENT",))
        if job.requires_approval and not job.approval_received:
            return ResumeDecision(WAITING_APPROVAL, False, ("APPROVAL_REQUIRED",))
        if not _risk_allows(job, False):
            return ResumeDecision(BLOCKED, False, ("RISK_NOT_RESUMABLE",))
        return ResumeDecision(READY, True, ("RESUME_PRECONDITIONS_SATISFIED",))
    except Exception:
        return ResumeDecision(FAILED_SAFE, False, ("INTERNAL_RESUME_ERROR",))


RETRYABLE_ERRORS = frozenset({"TEMPORARY_NETWORK_FAILURE", "TRANSIENT_FILE_LOCK", "RETRYABLE_LOCAL_ERROR"})
NON_RETRYABLE_ERRORS = frozenset({
    "AUTHENTICATION_FAILURE", "PERMISSION_DENIED", "POLICY_VIOLATION",
    "MALFORMED_OFFICIAL_EVIDENCE", "GATE_CONFLICT", "SECRET_ERROR",
    "DESTRUCTIVE_OPERATION_FAILURE",
})


def assess_retry(job: JobContract, error_code: Any) -> RetryDecision:
    try:
        if not validate_job(job)[0] or not isinstance(error_code, str) or SAFE_CODE.fullmatch(error_code) is None:
            return RetryDecision(FAILED_SAFE, False, ("RETRY_INPUT_INVALID",))
        if job.attempt_count >= job.max_attempts:
            return RetryDecision(FAILED_SAFE, False, ("MAX_ATTEMPTS_REACHED",))
        if error_code in NON_RETRYABLE_ERRORS or job.retry_policy == "NONE":
            return RetryDecision(FAILED_SAFE, False, ("ERROR_NOT_RETRYABLE",))
        if error_code in RETRYABLE_ERRORS and job.retry_policy in {"TRANSIENT_ONLY", "EXPLICIT_LOCAL"}:
            return RetryDecision(RETRY_WAIT, True, ("RETRY_WINDOW_REQUIRED",))
        return RetryDecision(FAILED_SAFE, False, ("ERROR_NOT_RETRYABLE",))
    except Exception:
        return RetryDecision(FAILED_SAFE, False, ("INTERNAL_RETRY_ERROR",))


def apply_approval(job: JobContract, *, approval_event_received: bool) -> JobContract:
    if not isinstance(approval_event_received, bool) or not approval_event_received or not job.requires_approval:
        return replace(job, state=WAITING_APPROVAL, approval_received=False)
    return replace(job, state=READY, approval_received=True)


@dataclass(frozen=True)
class JobTransitionResult:
    transition_version: str
    job_id: str | None
    job_type: str | None
    previous_state: str | None
    new_state: str | None
    occurred_at: str | None
    transition_status: str
    reason_code: str

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def validate_approval_transition(previous: Any, candidate: Any, *,
                                 approval_event_received: Any) -> bool:
    """Validate only the existing approval operation, not arbitrary state pairs.

    All job fields must match the existing Core operation's result. A matching
    state pair alone is insufficient. Completion/retry/resume are not implied.
    """
    try:
        return (
            type(approval_event_received) is bool
            and type(previous) is JobContract and type(candidate) is JobContract
            and validate_job(previous)[0] and validate_job(candidate)[0]
            and previous.state != candidate.state
            and candidate == apply_approval(previous, approval_event_received=approval_event_received)
        )
    except Exception:
        return False


def apply_approval_with_transition(job: Any, *, approval_event_received: Any
                                   ) -> tuple[JobContract | None, JobTransitionResult]:
    """Pure opt-in API: new immutable job plus a once-stamped transition result.

    No persistence or automatic approval. Existing apply_approval is unchanged.
    Unsupported/invalid input returns no updated job and no untrusted metadata.
    """
    rejected = JobTransitionResult(TRANSITION_VERSION, None, None, None, None,
                                   None, "REJECTED", "APPROVAL_TRANSITION_INVALID")
    try:
        if (type(job) is not JobContract or not validate_job(job)[0]
                or type(approval_event_received) is not bool):
            return None, rejected
        updated = apply_approval(job, approval_event_received=approval_event_received)
        if not validate_job(updated)[0]:
            return None, rejected
        if updated.state == job.state:
            return updated, JobTransitionResult(
                TRANSITION_VERSION, job.job_id, job.job_type, job.state, updated.state,
                None, "UNCHANGED", "NO_STATE_TRANSITION")
        if not validate_approval_transition(job, updated, approval_event_received=approval_event_received):
            return None, rejected
        # Generate only once, after the Core operation and validation succeed.
        occurred_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return updated, JobTransitionResult(
            TRANSITION_VERSION, job.job_id, job.job_type, job.state, updated.state,
            occurred_at, "APPLIED", "APPROVAL_STATE_TRANSITION")
    except Exception:
        return None, rejected


def validate_completion_transition(previous: Any, candidate: Any, *, expected_job_id: Any) -> bool:
    """Core-owned completion validation: identity match, RUNNING -> DONE only."""
    try:
        return (
            type(previous) is JobContract and type(candidate) is JobContract
            and type(expected_job_id) is str and _safe_text(expected_job_id)
            and previous.job_id == expected_job_id
            and validate_job(previous)[0] and validate_job(candidate)[0]
            and previous.state == RUNNING and candidate.state == DONE
            and candidate == replace(previous, state=DONE)
        )
    except Exception:
        return False


def complete_job(job: Any, *, expected_job_id: Any
                 ) -> tuple[JobContract | None, JobTransitionResult]:
    """Explicit in-memory completion; no persistence, cleanup or notification.

    The caller supplies its current job and expected identity, and must retain the
    returned job as the next state. DONE input rejects without another timestamp.
    This API cannot detect replay of an obsolete RUNNING snapshot.
    """
    rejected = JobTransitionResult(TRANSITION_VERSION, None, None, None, None,
                                   None, "REJECTED", "COMPLETION_TRANSITION_INVALID")
    try:
        if (type(job) is not JobContract or type(expected_job_id) is not str
                or not _safe_text(expected_job_id) or job.job_id != expected_job_id
                or not validate_job(job)[0] or job.state != RUNNING):
            return None, rejected
        updated = replace(job, state=DONE)
        if not validate_completion_transition(job, updated, expected_job_id=expected_job_id):
            return None, rejected
        occurred_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        result = JobTransitionResult(
            TRANSITION_VERSION, job.job_id, job.job_type, RUNNING, DONE,
            occurred_at, "APPLIED", "JOB_COMPLETION_TRANSITION")
        return updated, result
    except Exception:
        return None, rejected


def validate_failed_safe_transition(previous: Any, candidate: Any, *, expected_job_id: Any) -> bool:
    """New v0.1 semantics: explicit RUNNING -> FAILED_SAFE, no inferred failure."""
    try:
        return (
            type(previous) is JobContract and type(candidate) is JobContract
            and type(expected_job_id) is str and _safe_text(expected_job_id)
            and previous.job_id == expected_job_id
            and validate_job(previous)[0] and validate_job(candidate)[0]
            and previous.state == RUNNING and candidate.state == FAILED_SAFE
            and candidate == replace(previous, state=FAILED_SAFE)
        )
    except Exception:
        return False


def fail_job_safe(job: Any, *, expected_job_id: Any
                  ) -> tuple[JobContract | None, JobTransitionResult]:
    """Explicit in-memory failure confirmation, never triggered by a decision.

    No retry, approval, checkpoint, persistence or notification side effects.
    FAILED_SAFE input rejects; replay of an old RUNNING snapshot is not detected.
    """
    rejected = JobTransitionResult(TRANSITION_VERSION, None, None, None, None,
                                   None, "REJECTED", "FAILED_SAFE_TRANSITION_INVALID")
    try:
        if (type(job) is not JobContract or type(expected_job_id) is not str
                or not _safe_text(expected_job_id) or job.job_id != expected_job_id
                or not validate_job(job)[0] or job.state != RUNNING):
            return None, rejected
        updated = replace(job, state=FAILED_SAFE)
        if not validate_failed_safe_transition(job, updated, expected_job_id=expected_job_id):
            return None, rejected
        occurred_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        result = JobTransitionResult(
            TRANSITION_VERSION, job.job_id, job.job_type, RUNNING, FAILED_SAFE,
            occurred_at, "APPLIED", "FAILED_SAFE_CONFIRMED")
        return updated, result
    except Exception:
        return None, rejected


def create_event(**kwargs: Any) -> NotificationEvent | None:
    try:
        expected = {"event_version", "event_type", "job_id", "job_type", "severity", "state", "approval_required", "summary_code", "occurred_at"}
        if set(kwargs) != expected:
            return None
        event = NotificationEvent(**kwargs)
        values = (event.job_id, event.job_type, event.summary_code)
        if (
            event.event_version != EVENT_VERSION or event.event_type not in EVENT_TYPES
            or event.severity not in SEVERITIES or event.state not in JOB_STATES
            or not isinstance(event.approval_required, bool)
            or not _safe_text(event.job_id) or not _safe_text(event.job_type)
            or not isinstance(event.summary_code, str) or SAFE_CODE.fullmatch(event.summary_code) is None
            or _time(event.occurred_at) is None
            or any(FORBIDDEN_NAMES.search(value) or URL.search(value) or ABSOLUTE_PATH.search(value) for value in values)
        ):
            return None
        return event
    except Exception:
        return None


__all__ = [
    "FAILED_SAFE_CONTRACT_VERSION", "fail_job_safe", "validate_failed_safe_transition",
    "COMPLETION_CONTRACT_VERSION", "complete_job", "validate_completion_transition",
    "TRANSITION_VERSION", "JobTransitionResult", "apply_approval_with_transition",
    "validate_approval_transition",
    "APPROVAL_REQUIRED", "BLOCKED", "CANCELLED", "CHECKPOINTED", "DONE",
    "EVENT_TYPES", "EVENT_VERSION", "EXTERNAL_READ", "FAILED_SAFE",
    "JOB_STATES", "LOW_RISK_LOCAL", "NotificationEvent", "PROHIBITED_UNATTENDED",
    "QUEUE_VERSION", "READ_ONLY", "READY", "RETRY_WAIT", "RISK_CLASSES",
    "RUNNING", "WAITING_APPROVAL", "Checkpoint", "JobContract", "QueueDecision",
    "ResumeDecision", "RetryDecision", "apply_approval", "assess_retry",
    "create_checkpoint", "create_event", "resume_from_checkpoint",
    "select_next_job", "switch_after_pause", "validate_checkpoint", "validate_job",
    "validate_queue",
]
