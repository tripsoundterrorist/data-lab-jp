# QUEUE_BLOCKED Event Dispatch v0.1

## Purpose and ownership

`dispatch_queue_blocked(decision, identity, *, mode="DRY_RUN", ...)` connects
existing QueueBlockedDecision and QueueIdentity through
build_queue_blocked_safe_event to existing Runtime.process_notification.
The caller obtains the decision from Core assess_queue_blocked and the identity
from its formal Core contract. Dispatch never examines a queue snapshot.

Factory is the sole canonical event metadata source and delegates Decision and
Identity validation to Core. Dispatch has no event dict literal, metadata matrix,
queue identifier constant, timestamp generator, hash or second input validator.
Factory failure/exception or non-event return yields BLOCKED, event_generated=false,
runtime_handoff=false. QUEUE_IDLE, NOT_BLOCKED and UNKNOWN therefore never become
notifications. Factory success is passed as the same object, without modification.
Runtime still validates the event schema before delivery.

## Schema and downstream responsibilities

Factory owns the exact v0.2 QUEUE event, real queue_id, fixed metadata and exact
Decision occurred_at propagation. No fake job fields. Equal Decision/Identity
inputs yield equal events. Runtime owns canonical JSON/SHA-256 identity; different
occurrence timestamps produce different identities. v0.2 subject separation
isolates queue identity from the existing three job-level notification events.

Runtime owns Recovery, Ledger, Adapter and Sender. No direct calls to these
components exist in Dispatch. Factory owns severity; Adapter owns priority 1,
IMMEDIATE and the existing message. Runtime/Ledger suppress duplicate deliveries
before Sender and persist only existing safe delivery metadata.

## Modes and result

This version accepts DRY_RUN (default) and MOCK_RUNTIME only. Other modes are
blocked before Factory/Runtime; no CLI or LIVE activation is provided. Mock
requires explicit callable credential-loader/transport fixtures. Optional ledger
is passed only to Runtime, which enforces mock storage isolation. Tests use temp
Ledger and mock transport, never production sending. Runtime modes themselves
are unchanged. Any future LIVE support needs a separate approval/gate.

Immutable BlockedDispatchResult contains exactly dispatch_version,
dispatch_status, event_generated, runtime_handoff, runtime_mode, runtime_status,
reason_code. It omits event identity, event body, identifiers and raw downstream
reasons. Runtime status is allowlisted; malformed responses fail safely.
runtime_handoff means the call was attempted, not proof of delivery. An exception
after handoff cannot prove that no delivery occurred. No retry is performed.

## Isolation, security and limitations

No mutation of jobs, Decision, Identity, approval, checkpoint, dependencies,
retry, scheduling, priority or ordering. Notification/Runtime/Sender/Ledger
failure cannot unblock work or trigger repair, retry, switch or approval.
Temporary mock Ledger writes are Runtime responsibility, not Queue mutations.
No secrets, raw event/payload/response, notification message or exception text
are included in Dispatch output. CRITICAL_STOP is not generated or inferred;
the existing emergency sending ban remains unchanged.

Contract validation is not cryptographic origin authentication, persisted
Decision proof, durable history, replay prevention or stale-snapshot detection.
QueueIdentity is not a credential. Directly constructed contract-valid sources
can pass. Ledger provides only best-effort notification identity deduplication
with its existing delivery/record crash window.

## Non-goals and next gate

No changes to existing Job-Level Dispatch, Factory, Core, schema, Runtime,
Adapter, Sender or Ledger. No production Ledger/Queue/data writes, Scheduler or
power changes, LIVE activation, Stage C/D, deployment, commit or push. Stage C
four-event integrated validation may be considered only after separate approval
of this dedicated Dispatch; it is not performed here.
