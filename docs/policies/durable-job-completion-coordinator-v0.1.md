# Durable Job Completion Coordinator Contract v0.1

## Scope

The coordinator persists a confirmed `RUNNING -> DONE` transition for one exact
execution generation. It does not invoke an Executor, infer success, handle
failed execution, delete checkpoints, dispatch notifications, or activate
production Queue writes.

## Generation binding

The caller supplies `expected_job_id` and `expected_attempt_count`. The loaded
Queue must contain exactly that job and generation in `RUNNING`. A missing,
invalid, stale, or different generation rejects before Core completion or any
save. This prevents an obsolete completion signal from completing a newer run.

## Required sequence

The coordinator loads a healthy Queue, delegates completion and validation to
Core, replaces only the selected job, and performs exactly one expected-revision
CAS save. Persistence's `SAVED` result is the durable boundary because
Persistence already completed atomic replacement and exact internal read-back.
The coordinator must not issue a second `load_queue()` after `SAVED`.

Locks, stale revisions, temporary residue, failed saves, uncertain read-back,
and mismatches fail closed without retry. A stale revision returns
`COMPLETION_CONFLICT` and `durable=false`. An observationally uncertain save
returns `JOB_COMPLETION_UNCERTAIN`, `RECOVERY_BLOCKED`, and `durable=false`.
Neither path retries, rolls back, saves again, nor changes the attempt count.

Successful completion returns `JOB_COMPLETED_DURABLY`,
`JOB_COMPLETION_DURABLE`, and `durable=true`. Results expose only fixed codes and
safe identity, generation, and revision fields.

## Deferred and non-goals

Production writes remain disabled. Executor result authentication, durable
failed-safe coordination, checkpoint cleanup, notification dispatch, leases,
heartbeats, retries, and automatic recovery are deferred.

## Next gate

`Durable Job Failed-Safe Coordinator Contract v0.1` should persist a confirmed
`RUNNING -> FAILED_SAFE` transition for one exact execution generation without
retrying, notifying, or enabling production writes.
