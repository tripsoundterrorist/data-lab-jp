# Durable Execution Adoption Coordinator Contract v0.1

## Scope

The coordinator connects the existing pure execution-adoption Core contract to
Queue Persistence CAS and read-back. It covers only durable `READY -> RUNNING`
adoption. It does not invoke an Executor, resume checkpoints, retry jobs,
bootstrap production storage, deliver notifications, or activate production.

## Required sequence

The coordinator loads one healthy persisted snapshot, delegates selection and
candidate creation to Core, validates the returned transition, replaces only the
selected job, and performs exactly one expected-revision CAS save. Persistence's
`SAVED` result is the durable boundary because Persistence already completed its
atomic replacement and exact internal read-back. The coordinator must not issue
a second `load_queue()` after `SAVED`.

`attempt_count` is consumed only after CAS and read-back confirmation. A stale
revision, lock, temporary residue, failed save, uncertain read-back, or mismatch
fails closed. The coordinator does not retry because a failed response can be
observationally ambiguous. A stale revision returns `ADOPTION_CONFLICT` with
`durable=false` and is never retried. An observationally uncertain save returns
`EXECUTION_ADOPTION_UNCERTAIN`, `RECOVERY_BLOCKED`, and `durable=false`; it never
rolls back, saves again, or decrements an attempt.

Successful adoption returns `EXECUTION_ADOPTED_DURABLY`,
`EXECUTION_ADOPTION_DURABLE`, and `durable=true`.

## Fresh route and checkpoint references

Before Core adoption, the coordinator rejects a target job that has an active
checkpoint reference with `FRESH_ROUTE_CHECKPOINT_REFERENCE_PRESENT`. A
checkpoint reference belonging to another job does not block an otherwise valid
fresh route. The coordinator never deletes or rewrites checkpoint references.

## Ownership boundaries

Core owns selection, risk and approval eligibility, attempt increment semantics,
and transition validation. Queue Persistence owns serialization, locking, CAS,
atomic replacement, and its internal read-back. The coordinator only sequences
those owners and confirms the resulting generation.

The result exposes only fixed status and reason codes plus safe job identity,
attempt count, and Queue revision. Raw exceptions, paths, credentials, payloads,
and storage documents never cross the boundary.

## Deferred and non-goals

Production Queue writes remain disabled. Executor invocation, execution leases,
heartbeats, completion coordination, failed-safe persistence, checkpoint resume,
retry adoption, notification dispatch, and automatic recovery are deferred.

## Next gate

`Durable Job Completion Coordinator Contract v0.1` should persist a confirmed
`RUNNING -> DONE` transition for an already adopted generation without invoking
an Executor or enabling production writes.
