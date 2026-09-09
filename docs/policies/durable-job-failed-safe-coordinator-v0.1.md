# Durable Job Failed-Safe Coordinator Contract v0.1

## Scope

The coordinator persists an explicitly confirmed `RUNNING -> FAILED_SAFE`
transition for one exact execution generation. It does not infer failure, invoke
an Executor, retry, delete checkpoints, dispatch notifications, or activate
production Queue writes.

## Generation binding and sequence

The caller supplies `expected_job_id` and `expected_attempt_count`. The loaded
Queue must contain exactly that job and generation in `RUNNING`. Missing,
invalid, stale, or different generations reject before Core or persistence is
called. Core remains authoritative for the candidate and transition result.

The coordinator validates Core's `FAILED_SAFE_TRANSITION`, replaces only the
selected job, and performs exactly one expected-revision CAS save. Persistence's
`SAVED` result is the durable boundary after atomic replacement and internal
read-back. The coordinator performs no second load after `SAVED`.

Locks, stale revisions, temporary residue, save failures, and uncertain
read-back fail closed without retry or rollback. A stale revision returns
`FAILED_SAFE_CONFLICT`. An observationally uncertain save returns
`JOB_FAILED_SAFE_UNCERTAIN`, `RECOVERY_BLOCKED`, and `durable=false`.

Success returns `JOB_FAILED_SAFE_DURABLY`, `JOB_FAILED_SAFE_DURABLE`, and
`durable=true`. Results expose only fixed codes and safe identity, generation,
and revision fields.

## Deferred and non-goals

Production writes remain disabled. Failure inference, executor result
authentication, checkpoint cleanup, notification dispatch, retry adoption,
leases, heartbeats, and automatic recovery are deferred.

## Next gate

A separate executor-result authentication contract must define how a caller may
prove completion or safe failure for an exact adopted generation. It must not
enable an Executor, production writes, notification dispatch, or infer outcomes
from free-form text.
