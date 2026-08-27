# Job Transition Result Validation Contract v0.1

## Purpose and API

`validate_job_transition_result(result)` is a read-only Queue Core contract check.
It returns frozen TransitionValidationResult with validation_version, valid,
transition_class and reason_code; to_dict returns a copy. Only a fully matching
APPLIED contract yields valid=true / TRANSITION_CONTRACT_VALID. All other inputs
yield valid=false / UNSUPPORTED / TRANSITION_RESULT_INVALID without raw metadata.
REJECTED and UNCHANGED are not accepted as applied event sources, even when their
own rejection/no-change shape is legitimate. This API is not a general schema
validator for those other statuses. Valid does not mean a notification must occur.

## Exact contract and existing classes

Input must be exactly JobTransitionResult with exactly its eight instance fields,
all strings, transition_version=0.1 and transition_status=APPLIED. Identifiers reuse
Core's existing _safe_text rules, not a second regex. States must be existing
JOB_STATES and must differ. Pair/reason consistency is owned by Core:

| Existing operation reason | Pair constraint | transition_class |
|---|---|---|
| APPROVAL_STATE_TRANSITION | Any existing distinct source -> WAITING_APPROVAL | APPROVAL_WAITING_TRANSITION |
| APPROVAL_STATE_TRANSITION | Any existing distinct source -> READY | APPROVAL_READY_TRANSITION |
| FAILED_SAFE_CONFIRMED | RUNNING -> FAILED_SAFE | FAILED_SAFE_TRANSITION |
| JOB_COMPLETION_TRANSITION | RUNNING -> DONE | COMPLETION_TRANSITION |

The approval rows reflect apply_approval's existing destination behavior, not a
new transition authorization. Tests generate these pairs through the existing
approval API across valid source-state fixtures. Full pre/post JobContract validation
still belongs to operation APIs: this reduced result omits approval flags and other
job fields and cannot reconstruct or prove them. No operation API is called while
validating a result. No new state-machine semantics is introduced.

## Timestamp and read-only behavior

occurred_at must parse as ISO-8601 datetime, be timezone-aware, and have UTC offset
zero. Z and +00:00 forms are accepted. Non-UTC offsets are rejected even if they
could be converted to UTC. The original string is never normalized, replaced or
regenerated. There is no current-time generation, freshness check or timestamp
comparison with a durable history. Input objects and all job/Queue/approval/
checkpoint/retry/scheduling state remain unchanged. No I/O is performed.

## Explicit trust limitations

A directly constructed but fully conforming result can pass. Malformed or
inconsistent direct constructions fail. This is contract validation only, not
authentication that Core actually produced the result. There are no signatures,
MACs, nonces, origin/process checks, durable logs, persisted-state proof,
cross-process history, stale-snapshot detection or replay protection. Historical
conforming timestamps can pass. Callers must not describe valid=true as provenance
or persistence evidence. Existing in-memory transition limitations remain.

## Dispatch boundary and non-goals

No Dispatch is implemented here. Future Dispatch must first call this validator,
require valid=true, and use transition_class for its own event mapping/suppression.
APPROVAL_READY_TRANSITION is a valid Core transition but is not the approval-wait
notification source. Dispatch must not copy pair, reason, identifier or timestamp
validation matrices. Queue classes are operation-domain names, not notification
event types. No Adapter, Sender, Ledger, Runtime, priority/class or LIVE coupling.

QueueDecision/queue_id and new QUEUE_BLOCKED semantics remain unsupported.
QUEUE_IDLE is not reinterpreted. No persistent journal or origin authentication is
added. No production Queue/Ledger/DB/Temporal/Publication/credential/power writes,
task changes, notification generation or delivery. All five Scheduler definitions
remain unchanged, with LIVE Disabled and no trigger.
