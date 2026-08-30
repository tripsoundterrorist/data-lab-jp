# Unattended Job Execution Adoption Contract v0.1

## Purpose and scope

This contract defines the pure Core candidate transition for a freshly selected
`READY` job. It covers only `READY -> RUNNING`; checkpoint resume, retry state
transitions, persistence coordination, execution, and production activation are
outside this contract.

## Attempt generation

`attempt_count` starts at zero. One attempt is one durably adopted `RUNNING`
ownership generation. Core creates a candidate by changing only `state` from
`READY` to `RUNNING` and incrementing `attempt_count` by exactly one. The logical
fresh-route generation is `(job_id, attempt_count)`. Queue revision identifies a
queue snapshot and is not an execution generation.

An adoption is allowed only while `attempt_count < max_attempts`. Equality is a
valid stored job but rejects fresh adoption with `ATTEMPTS_EXHAUSTED`; exceeding
the maximum is an invalid job contract. Attempts are never decremented or reset.

## Candidate and durable consumption

The Core function is pure and produces an immutable candidate plus the shared
`JobTransitionResult` with reason `JOB_EXECUTION_ADOPTION`. Candidate creation
does not itself prove durable attempt consumption. A later coordinator contract
must perform Queue CAS and read-back. CAS failure discards the candidate; a save
confirmed by read-back consumes the generation. Crash and uncertain read-back
handling belong to that coordinator contract.

## Revalidation and ownership

Core re-runs the existing queue selection against the supplied current queue and
explicit window/external-read facts. The expected job must still be selected.
Existing selection remains the source of truth for approval, risk, dependencies,
blockers, deadline windows, priority, and the attempt boundary.

Core owns candidate transition and increment semantics. Persistence may only
store/restore and perform CAS. The future coordinator owns durable confirmation.
Executor consumes a confirmed generation and must not increment it.

## Result validation

The dedicated validator requires an unchanged job identity, `READY -> RUNNING`,
exactly `+1`, no other field changes, a timezone-aware UTC timestamp supplied by
the caller, and the fixed adoption reason. No `started_at` or `execution_id` is
added to `JobContract`.

## Deferred and non-goals

`RESUME_ATTEMPT_SEMANTICS_DEFERRED`: this fresh route does not interpret an active
checkpoint reference and does not modify `resume_from_checkpoint()`. Retry state
transitions are also deferred. There is no filesystem access, persistence, CAS,
Executor invocation, notification delivery, lease, heartbeat, Queue bootstrap,
checkpoint write, DB/Ledger write, or production activation in this contract.

## Next gate

`Durable Execution Adoption Coordinator Contract v0.1` will connect the Core
candidate to Queue Persistence CAS and read-back without starting an Executor.
