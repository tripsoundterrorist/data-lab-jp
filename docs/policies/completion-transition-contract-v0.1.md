# Completion Transition Contract v0.1

## Purpose and source of truth

Queue Core now formally owns an explicit RUNNING -> DONE completion API:
`complete_job(job, expected_job_id=...)`. This is a new, narrowly authorized
operation, not a reinterpretation of selection, approval, retry or resume behavior.
No Dispatch, notification or scheduler integration is implemented here.

## Preconditions and validation

The caller must supply its current exact JobContract and expected job identifier.
Core checks existence/type, safe matching identifier, every existing job validation
rule, current state RUNNING and the fixed target DONE. No other target is accepted.
`validate_completion_transition(previous, candidate, expected_job_id=...)` checks
the same requirements and full candidate equality to previous with only state=DONE.
READY, WAITING_APPROVAL, FAILED_SAFE, BLOCKED, DONE and all other non-RUNNING states
are rejected. A valid DONE snapshot alone is not evidence of a completion operation.

## Result and atomic in-memory behavior

The return shape is `(updated_job, JobTransitionResult)`, reusing the frozen schema:
transition_version, job_id, job_type, previous_state, new_state, occurred_at,
transition_status, reason_code. Successful results use APPLIED and
JOB_COMPLETION_TRANSITION. The input is never modified. Core constructs a frozen
candidate, validates it, generates UTC time once, then returns both together.
If any step fails, it returns no updated job and REJECTED with a fixed safe reason
and null identity/state/time fields. No partial candidate is exposed or persisted.
Exceptions and unsafe identifiers are not echoed.

The timestamp is ISO-8601 UTC ending in Z, generated after candidate validation.
Repeated reads and serialization preserve it. created_at and all job fields except
state are unchanged. No state_updated_at or second timestamp authority is added.

## Repeated completion and persistence limitation

Callers must retain the returned DONE job as current state. Completing that job
again rejects without generating another timestamp. This is an in-memory value
API, not a persisted completion proof, durable log, lock or compare-and-swap store.
It cannot detect resubmission of an obsolete RUNNING snapshot. Reusing that stale
input is a new invocation, not an idempotent read; retain the original transition
result instead. Cross-process replay/concurrency and durable state commits require
a separately approved state owner. No such storage is added in v0.1.

## Separation and compatibility

Existing approval APIs, JobContract, QueueDecision, constructors and serialization
are unchanged. Checkpoints are not deleted or edited on completion. Cleanup,
approval, retries and job removal are separate responsibilities. No Queue persisted
state, Ledger, DB, Temporal, Publication, credentials, power or Scheduler writes.
No JOB_COMPLETED notification event, Adapter, Sender, priority, message or LIVE
logic is added. Production Ledger is read-only; LIVE Task stays Disabled/no trigger.

queue_id and new QUEUE_BLOCKED semantics remain unsupported. QUEUE_IDLE is not
QUEUE_BLOCKED and selection semantics remain unchanged.

## Dispatch resumption

The approval-only transition contract remains unchanged; this separate contract
supersedes its historical completion-API limitation only for RUNNING -> DONE.
Completion can now provide job_id, job_type, previous/new state, fixed occurred_at
and Core validity for a future job-level JOB_COMPLETED dispatch. Other events need
their own verified source. QUEUE_BLOCKED remains unsupported for real-Queue dispatch.
Dispatch and any future LIVE activation still require separate implementation,
review and approval. This change performs only in-memory tests, never real delivery.
