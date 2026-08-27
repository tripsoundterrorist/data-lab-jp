# Queue Blocked Decision Contract v0.1

## Purpose and compatibility

`assess_queue_blocked(jobs, *, window_states=None, external_read_allowed=False)`
is an opt-in, read-only Queue Core API. Existing JobContract, QueueDecision,
select_next_job, switch, approval, retry and checkpoint semantics are unchanged.
QUEUE_BLOCKED is a queue-domain decision, not a new job state or notification.

Existing select_next_job returns QUEUE_IDLE whenever no job is eligible, including
paused work. It also already returns QUEUE_BLOCKED for invalid input and internal
errors. Neither value proves the new contract. Do not reinterpret legacy results.
QUEUE_IDLE != QUEUE_BLOCKED.

## Exact proof boundary

1. Validate the complete supplied queue using existing validate_queue, including
   identifiers, dependency membership and existing cycle detection. Invalid input,
   unknown dependencies, cycles or invalid context return UNKNOWN, blocked=false.
2. Evaluate existing select_next_job with the same context. Any RUNNING job or
   eligible READY job means NOT_BLOCKED. Unrelated READY work therefore prevents
   blockage even when approval-waiting or failed jobs exist.
3. Empty/all-DONE snapshots return QUEUE_IDLE / NO_REMAINING_WORK.
4. Proven roots are WAITING_APPROVAL with requires_approval=true and
   approval_received=false, or FAILED_SAFE. These states cannot be selected by
   the existing scheduler. FAILED_SAFE alone is blocked in this snapshot sense;
   it is not a claim of permanent irrecoverability or an automatic retry decision.
5. A READY job with at least one dependency in the proven set is also stopped:
   existing selection requires every dependency DONE. Propagate that fact over
   existing dependency edges until no further READY jobs can be proven stopped.
6. Only when EVERY non-DONE job belongs to that proven set return QUEUE_BLOCKED.
   Otherwise return UNKNOWN / BLOCKAGE_NOT_PROVEN, never guessed blockage.

Unknown residual CHECKPOINTED, RETRY_WAIT, CANCELLED, BLOCKED, arbitrary blocker
codes, missing window facts, risk denials, or approval-flag contradictions are
not independently classified as proven blockers. Their recovery context is not
provided here. READY awaiting approval without a dependency proof is conservatively
UNKNOWN. CANCELLED terminal-work accounting is not newly defined; only DONE is
excluded from remaining_job_count. Invalid input reports count=0, not a trusted
count of the malformed input. UNKNOWN does not authorize execution.

## Schema and classification

Frozen QueueBlockedDecision has exactly seven fields:
decision_version, decision_status, blocked, occurred_at, blocker_class,
reason_code, remaining_job_count.

| Blocker class | Fixed reason |
|---|---|
| APPROVAL_BLOCKED | APPROVAL_REQUIRED_FOR_PROGRESS |
| FAILED_SAFE_BLOCKED | FAILED_SAFE_PREVENTS_PROGRESS |
| MIXED_BLOCKED | MULTIPLE_PROVEN_BLOCKERS |

Dependency descendants retain their root classification; no independent
DEPENDENCY_BLOCKED class is invented. MIXED means both root types are present.
No IDs, blocker-code payload, credentials, free-form reasons or raw errors are
returned. Nonblocked results use class NONE and no timestamp. Other fixed reasons
are QUEUE_INPUT_INVALID, NO_REMAINING_WORK, RUNNING_JOB_PRESENT,
ELIGIBLE_READY_JOB_PRESENT, BLOCKAGE_NOT_PROVEN.

## Time and validation ownership

Core generates UTC occurred_at exactly once after a positive proof. Reading or
serializing the result never regenerates it. Nonblocked/UNKNOWN results have no
blocked timestamp. A new assessment is a new observation and may have a new time.

`validate_queue_blocked_decision(decision) -> bool` validates exact result type,
seven-field schema, version, positive blocked status, aware UTC timestamp, fixed
class/reason agreement and positive integer count (not bool). MIXED requires at
least two jobs. It returns false for malformed, nonblocked or UNKNOWN results.
This is a blocked-result contract check, not notification eligibility or proof of
the original queue. Deserialize explicitly into QueueBlockedDecision if needed;
raw dicts are not accepted. Future Dispatch must use this Core validator rather
than reimplementing the proof conditions.

## Safety and limitations

No job mutation, approval, checkpoint operation, retry, scheduling change, switch,
dependency repair or automatic recovery. The selector is queried but its action
is never executed. No Dispatch, Runtime, Adapter, Sender, Ledger or Pushover calls.
Tests use in-memory queue fixtures only. Production state is never written.

This is an in-memory evaluation of the caller-supplied snapshot, not origin
authentication, persisted queue decision proof, durable outbox, event sourcing,
replay protection, stale-snapshot detection or restart rediscovery history.
Directly constructed conforming results can validate. No queue_id source exists;
none is guessed from repo, host or a fixed value. Queue-level event identity still
requires a separately approved contract before future Dispatch integration.

## Non-goals and next gate

Do not change existing three-event Job-Level Dispatch or generate QUEUE_BLOCKED
notifications. After contract approval only, consider separate Core-validated
queue-level Dispatch and identity design. No LIVE activation, Scheduler changes,
production Ledger/Queue/DB/Temporal/Publication writes, credentials/power changes,
deploy, commit or push are part of this implementation.
