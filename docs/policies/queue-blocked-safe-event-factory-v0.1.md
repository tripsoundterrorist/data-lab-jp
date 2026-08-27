# Queue Blocked Safe Event Factory Contract v0.1

## Purpose and ownership

`build_queue_blocked_safe_event(decision, identity)` is the production-facing
source of canonical QUEUE_BLOCKED v0.2 notification metadata. Its contract
version is QUEUE_BLOCKED_FACTORY_VERSION = 0.1. Future Dispatch and integration
fixtures should call this factory rather than reconstructing metadata.

The factory first delegates to validate_queue_blocked_decision, then to
validate_queue_identity, requiring literal True. It never assesses queue work,
dependencies, blocker classes or reasons itself. Invalid, nonblocked, idle,
unknown or malformed sources and exceptions return None without exposing input
or exception content. The assembled output is validated by existing create_event.

## Canonical metadata

| Field | Source/value |
|---|---|
| event_version | Existing EVENT_SCHEMA_VERSION: 0.2 |
| subject_type | QUEUE |
| event_type | QUEUE_BLOCKED |
| severity | ERROR, explicitly approved for this factory contract |
| state | QUEUE_BLOCKED, queue-domain value |
| summary_code | QUEUE_BLOCKED, existing schema v0.2 fixed value |
| approval_required | false, existing notification approval semantics |
| queue_id | Valid QueueIdentity.queue_id, copied exactly |
| occurred_at | Valid QueueBlockedDecision.occurred_at, copied exactly |

approval_required is false because only JOB_WAITING_APPROVAL uses true in the
notification contract; it does not describe approval-waiting jobs inside a queue.
APPROVAL_BLOCKED, FAILED_SAFE_BLOCKED and MIXED_BLOCKED all use ERROR. Severity is
not derived from blocker class or delivery priority. Changing this canonical
mapping requires a versioned contract update. Generic schema validation still
accepts its existing severity set; that compatibility reader is not a second
canonical producer. Existing raw schema fixtures remain wire-format test vectors,
not a production configuration source.

## Output and boundaries

Success returns immutable QueueNotificationEventV02 with exactly nine fields.
No job_id/job_type, priority, delivery_class, message, raw decision, count or
blocker metadata is added. queue_id is never hard-coded here. No clock,
timestamp normalization, hashing, I/O or delivery occurs. Equal inputs produce
equal events; the decision's UTC spelling/precision is retained unchanged.

Runtime alone owns SHA-256/canonical JSON identity. Adapter alone owns priority
1 / IMMEDIATE and the existing fixed message. The factory calls neither Runtime,
Adapter, Sender, Recovery nor Ledger. Tests may separately inspect Adapter output
and Runtime identity without invoking notification processing.

## Read-only and trust limitations

No mutation of jobs, queue, approval, checkpoint, dependency, retry, priority,
scheduling or ordering; no automatic recovery. No production state writes.
Validation checks contract consistency, not cryptographic origin or persisted
decision proof. Directly constructed conforming objects can pass. Queue identity
is not authentication. This does not supply durable history, replay prevention,
stale-snapshot detection or cross-process provenance. Existing notification Ledger
deduplication is a separate best-effort mechanism, not a factory guarantee.

## Non-goals and next gate

No QUEUE_BLOCKED Dispatch or Runtime handoff, Stage C/D, LIVE notification,
Scheduler change, credential change, Sender change or Ledger migration. After
approval, future QUEUE_BLOCKED Dispatch can call this factory and hand its result
to the existing Runtime; it must not duplicate canonical metadata. This task
implements and tests the factory only, without commit or push.
