# Failed-Safe Transition Contract v0.1

## Explicitly approved new semantics

RUNNING -> FAILED_SAFE is newly formalized in v0.1 by explicit operator approval.
It is not claimed as a pre-existing transition inferred from retry/resume decisions.
Queue Core is the only state-machine source of truth. No Dispatch or Runtime
connection, notification generation or LIVE activation is part of this change.

## API, preconditions and scope

`fail_job_safe(job, expected_job_id=...)` explicitly confirms failure of the current
in-memory RUNNING JobContract. As with complete_job, expected_job_id is a required
keyword argument. Core checks exact JobContract type, all existing validation,
safe matching job identity and RUNNING state. FAILED_SAFE is the fixed target.
`validate_failed_safe_transition(previous, candidate, expected_job_id=...)`
also requires complete candidate equality to previous with only state changed.

READY, WAITING_APPROVAL, CHECKPOINTED, DONE, FAILED_SAFE, BLOCKED, RETRY_WAIT,
CANCELLED and unknown source states are rejected. No other transition is authorized.
Callers explicitly decide to invoke this API; it does not infer execution failure
from text, exceptions, logs, retry assessments or checkpoint rejection.

## Shared result and timestamp

Return value: `(updated_job, JobTransitionResult)`. Reuses the frozen eight fields:
transition_version, job_id, job_type, previous_state, new_state, occurred_at,
transition_status, reason_code. The input is immutable and never changed.
After precondition checks, Core constructs and validates a candidate, then stamps
UTC once (ISO-8601 with Z) and returns both values. Serialization/re-reading does
not generate time. Success is APPLIED / FAILED_SAFE_CONFIRMED.

Invalid input, candidate failure or exception returns no updated job and REJECTED /
FAILED_SAFE_TRANSITION_INVALID with null identifying/state/time fields. No partial
candidate escapes; no successful transition timestamp is issued for rejected input.
Free-form reason, exception, credential, payload, command, message and PII fields
are not accepted or echoed. A clock failure leaves the input unchanged.

## Repeated invocation and persistence limitation

Retain the returned FAILED_SAFE job as current state. Repeating on it rejects
without a new occurred_at. The result is an in-memory operation result only, not
a durable journal, persisted proof, cross-process history, stale snapshot detector
or replay protection. Re-submitting an old RUNNING snapshot can create another
result; that limitation is explicitly outside v0.1. No persistent version/CAS or
state store is added. Retain the result instead of reconstructing it by re-running.

## Existing responsibilities remain separate

assess_retry() remains a decision-only API and never calls fail_job_safe().
resume_from_checkpoint() rejection likewise does not perform a job transition.
Neither API's behavior or return schema changes. Failure confirmation does not
start retries, schedule work, create/approve/reject approvals, or create/update/
delete checkpoints. All fields other than state, including approval flags,
priority, attempts and creation time, are preserved. Cleanup is a separate concern.
Approval, completion, switching, scheduling and select_next_job remain unchanged.

No Adapter/Sender/Ledger/Runtime calls or notification priority/class/messages are
added. No production Queue, Ledger, DB, Temporal, Publication, credential, power
or Scheduler writes. Tests use in-memory fixtures. LIVE Task stays Disabled without
triggers, and all five task definitions remain unchanged.

## Non-goals and Dispatch prerequisites

queue_id and new QUEUE_BLOCKED semantics remain unsupported. QUEUE_IDLE is not
reinterpreted as QUEUE_BLOCKED. No failure event is generated here.
Together with the existing approval and completion contracts, job-level structured
sources for future WAITING_APPROVAL, FAILED_SAFE and COMPLETED notification mapping
are now available. A separately approved Dispatch implementation may consume valid
APPLIED results, preserving their identity fields and timestamps. It must not infer
transitions from decision-only outputs. QUEUE_BLOCKED remains excluded by a separate
unmet gate. No Dispatch implementation or notification execution occurs here.
