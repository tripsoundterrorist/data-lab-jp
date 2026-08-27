# Four Notification Events Integrated Validation v0.1

## Scope

Stage C verifies existing production code without changing it. Formal Core
approval-waiting, failed-safe and completion results use Job-Level Dispatch.
Core QueueBlockedDecision plus QueueIdentity uses Queue Blocked Dispatch and
its existing Factory. All event generation/validation, identity, Recovery,
Ledger, Adapter and Sender logic is the existing implementation.

## Evidence

tests/test_four_event_notification_integration.py exercises all four event kinds:
JOB_WAITING_APPROVAL, JOB_FAILED_SAFE, JOB_COMPLETED and QUEUE_BLOCKED.
For each, DRY_RUN generates an event and hands off without transport or writes;
the identical source reproduces the same event and Runtime identity. Mock first
delivery adds a record to a temporary Ledger. Second delivery is persistently
suppressed before Sender. A shared temp Ledger also records all four identities
and suppresses all four repeats. All six cross-event pairs have distinct IDs.

Adapter remains authoritative: waiting, failed-safe and queue-blocked use
1 / IMMEDIATE; completion uses 0 / NORMAL. CRITICAL_STOP remains
EMERGENCY_SEND_BLOCKED under mock transport, never LIVE.

Approval-ready produces no notification. JOB_STARTED, JOB_CHECKPOINTED,
JOB_SWITCHED and QUEUE_IDLE remain Runtime-suppressed. UNKNOWN and idle queue
decisions produce no event/handoff. UNKNOWN's Dispatch status is BLOCKED, not
SUPPRESSED: suppression here means no notification, not a status rename.

Both Dispatch families are tested against Runtime, Sender and Ledger failures.
Source results, input jobs, identity and checkpoint fixtures remain unchanged.
No rollback, approval, retry, repair or unblock is performed. All writes in mock
processing are confined to temporary test Ledgers; production Ledger bytes are
checked unchanged. Broader DB/Temporal/Publication/Scheduler/power/credential
invariants are measured separately by read-only pre/post manifests and counts,
not inferred from these unit tests.

## Safety and limits

This is DRY_RUN/MOCK_RUNTIME evidence, not production execution or Scheduler
trigger provenance. Real transport and real credential loading are blocked in
the integrated fixture. No production source changes, LIVE, Scheduler edits,
production Ledger writes or deployment occur.

Origin authentication, persisted transition/decision proof, durable queue
history, replay and stale-snapshot protection remain absent. QueueIdentity is
not a security credential. Ledger dedupe is best-effort with the existing crash
window between API success and recording delivery. The dedicated LIVE Canary
Bridge remains approval-waiting-only. Completion of these tests does not grant
LIVE activation authority; Stage D is read-only and activation is a separate gate.
