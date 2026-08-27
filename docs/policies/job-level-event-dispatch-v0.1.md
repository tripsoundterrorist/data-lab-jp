# Job-Level Event Dispatch Integration v0.1

## Purpose and delegation

`dispatch_transition(source, mode="DRY_RUN", ...)` first calls Queue Core's
validate_job_transition_result. Only a supported, valid, versioned validation
response permits further work. Invalid/malformed results, exceptions and unknown
classes fail closed before event generation or Runtime invocation. Dispatch
contains no transition-pair/reason matrix or identifier/timestamp validator.
It checks the validator response contract, not the source's Core-owned rules.

## Mapping

| Core class | Dispatch outcome | Fixed severity / approval / summary_code |
|---|---|---|
| APPROVAL_WAITING_TRANSITION | JOB_WAITING_APPROVAL | WARN / true / APPROVAL_WAIT_TRANSITION |
| FAILED_SAFE_TRANSITION | JOB_FAILED_SAFE | ERROR / false / SAFE_FAILURE_TRANSITION |
| COMPLETION_TRANSITION | JOB_COMPLETED | INFO / false / COMPLETION_TRANSITION |
| APPROVAL_READY_TRANSITION | SUPPRESSED | No event |

Approval-ready suppression is normal, not an error. Unknown classes are not
mapped. QUEUE_BLOCKED, QueueDecision, QUEUE_IDLE reinterpretation, queue_id and
CRITICAL_STOP inference are excluded. Existing emergency blocking is unchanged.

## Event and identity ownership

Uses the existing nine-field Runtime event schema, with Core EVENT_VERSION and
fixed metadata above. job_id, job_type, state (new_state) and occurred_at are copied
from the validated source, never merged with another state snapshot. No clock,
normalization, timestamp replacement, random seed or hash computation exists here.
The same result produces the same safe event and existing Runtime SHA-256 identity.
Adapter alone owns message, priority, delivery class and emergency classification.

## Runtime modes and delivery

Only DRY_RUN and MOCK_RUNTIME are accepted. LIVE and unknown modes block without
an event/handoff. There is no CLI. Mock requires explicit callable fixture loader
and transport; optional internal dependencies are passed to Runtime, never operated
on by Dispatch. Runtime enforces isolated mock storage and owns Recovery preflight,
Ledger transactions, deduplication, Adapter and Sender calls. DRY_RUN never sends
or writes production Ledger. Mock tests use only temporary Ledger and fake transport.
Same-result second dispatch reaches Runtime's persistent dedupe and stops before
Sender; Dispatch maintains no separate delivery history.

## Safe result and isolation

Frozen DispatchResult has dispatch_version, dispatch_status, validation_version,
transition_class, event_generated, event_type, runtime_handoff, runtime_mode,
runtime_status, reason_code. Statuses are COMPLETED, SUPPRESSED, BLOCKED, FAILED_SAFE.
Only allowlisted Runtime statuses and fixed Dispatch reasons are returned. No raw
source, event, exception, credential, payload, response or notification text is
printed. runtime_handoff means the call was attempted, not proof of delivery.
After an exception it must not be interpreted as proof that nothing was sent.

Dispatch never changes jobs, approvals, checkpoints, retry decisions, scheduling
or Queue ordering. Runtime/Sender/Ledger failures leave the transition outcome
unchanged; no rollback, retry, cleanup or automatic approval is performed.
"Read-only" applies to Queue/source access: mock Runtime can write its temp Ledger.

## Trust and persistence limitations

Core validation is contract validation, not origin authentication. A conforming
direct construction can pass; Dispatch does not claim Core generated it. There are
no signatures, MACs, durable outbox, persisted event sourcing, restart rediscovery,
stale-snapshot detection or transition replay prevention. The existing Ledger
provides notification-identity best-effort deduplication only, with its existing
delivery/record crash window. Retain the original transition result for retries;
recreating a transition with a new timestamp changes identity.

## Non-goals and next gate

All five Scheduler definitions remain unchanged; LIVE stays Disabled/no trigger.
No production Ledger, Queue, DB, Temporal, Publication, credential or power changes,
deployment, real transport, LIVE enablement or recurring operation. Future LIVE
dispatch needs separate review/approval. Queue-level blocked dispatch additionally
requires a formal Queue Blocked Decision Contract; QUEUE_IDLE is not QUEUE_BLOCKED.
