# Notification Incident Suppression MOCK Runtime v0.1

Status: MOCK-only integration Gate.

## Contract

- After exact-event deduplication and before delivery, `MOCK_RUNTIME` evaluates
  the Incident Suppression Coordinator against an isolated Ledger snapshot.
- Suppression requires explicit matching v0.2 incident delivery evidence.
- Empty and v0.1-only snapshots continue to delivery and do not infer incident
  evidence.
- Coordinator blocking fails closed before adapter, credentials or transport.
- Selected reminders continue through the existing delivery path and are
  recorded as new exact v0.2 records.

## Preserved boundaries

- `LIVE_NOTIFICATION` does not invoke incident suppression and retains v0.1
  writes.
- `CRITICAL_STOP` continues through the existing emergency-send boundary.
- Exact-event deduplication remains first and unchanged.
- No existing record is migrated or rewritten.
- Approval rules, Executor writes and Production Queue writes are unchanged.
