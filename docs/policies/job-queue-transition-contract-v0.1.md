# Job Queue Transition Contract v0.1

## Purpose and source of truth

This is a deliberately partial, additive observation contract in Queue Core.
Only the already implemented `apply_approval` operation is formalized. Dispatch is
not implemented or resumed. No generic state setter or guessed transition matrix
is introduced. Queue remains the sole owner of operation semantics.

## API and schema

`apply_approval_with_transition(job, approval_event_received=bool)` returns
`(updated_job, JobTransitionResult)` without mutating the input or persisting it.
The updated job is a new frozen JobContract; the operator/caller remains responsible
for explicit approval input. No approval is automatically created or received.
The result is frozen with exactly transition_version, job_id, job_type,
previous_state, new_state, occurred_at, transition_status, reason_code.
`to_dict()` returns a copy. It includes no arbitrary message or notification data.

APPLIED means the in-memory state changed through the existing Core operation and
both contracts validate. Queue generates `datetime.now(timezone.utc)` once after
validation, encoded as ISO-8601 with Z. Reads/serialization never regenerate it.
This timestamp proves an in-memory result, not a durable transaction. Callers must
retain the result, not rerun the operation to reconstruct historical timestamps.
UNCHANGED means no state transition; occurred_at is null. Approval metadata can
still follow the legacy operation, but this status must not generate a state event.
REJECTED returns no updated job and null identifying/state/time fields with a fixed
safe reason. Input errors and exceptions never echo untrusted values.

## Validity responsibility and limits

`validate_approval_transition(previous, candidate, approval_event_received=bool)`
requires valid exact JobContracts, a boolean signal, a state change, and complete
candidate equality to the existing apply_approval result, including non-state
fields. A pair of state strings alone is not evidence. It does not validate
completion, retry or resume transitions. No Dispatch-side matrix is necessary for
this supported operation; consumers must use the Core-produced result.

The existing approval operation returns WAITING_APPROVAL/approval_received=false
when approval is absent or the job does not require approval, otherwise
READY/approval_received=true. The new API delegates unchanged; it does not impose
new scheduling, risk, retry or priority rules or reinterpret existing behavior.

RUNNING -> DONE is **not authorized by this new API**. DONE is an existing valid
state used by selection/dependency logic, but there is no existing completion
operation or transition guarantee to formalize. Validating a DONE snapshot does
not prove a legitimate completion transition. Completion remains an explicit
missing API requiring a separately approved Core contract; no pair is invented.
Retry/ResumeDecision are decisions, not proof that a state change was committed.

## Compatibility and QueueDecision limitations

JobContract fields, constructors, created_at, serialization and existing APIs remain
unchanged. The transition result is the sole new timestamp source; no duplicate
state_updated_at is added. QueueDecision is unchanged. There is no authoritative
queue_id source, so no constant, inferred ID or decision timestamp is invented.

QUEUE_IDLE != QUEUE_BLOCKED. In particular select_next_job's lack of eligible jobs
remains QUEUE_IDLE. Existing validation-error decisions are untouched; no new
queue-level blocked semantics is implemented. Real-Queue QUEUE_BLOCKED dispatch
remains blocked until a formal decision identity/time/blocked API is provided.

## Isolation, non-goals and Dispatch resumption

No Pushover, Adapter, Sender, Ledger, notification priority/message, LIVE/DRY mode,
Scheduler, DB, persisted Queue, checkpoint, Temporal, Publication or credential
coupling is added. Tests use in-memory fixtures. No automatic approval, execution,
retry, repair or production writes occur. All five tasks remain unchanged; LIVE
stays Disabled with no trigger. Production Ledger remains read-only.

Dispatch may only resume for a supported, Core-guaranteed transition carrying
job_id, job_type, previous_state, new_state and fixed occurred_at. Approval
transitions now meet that narrow requirement. Completion and other unsupported
operations do not; full Event Dispatch Integration remains incomplete. Queue-level
BLOCKED dispatch has separate unmet prerequisites described above.
