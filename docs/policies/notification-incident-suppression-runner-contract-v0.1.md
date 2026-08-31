# Notification Incident Suppression Runner Contract v0.1

Status: end-to-end regression Gate; no production behavior change.

## Verified path

- Scheduled Runtime Runner preflight and lock acquisition remain before Runtime.
- A persisted v0.2 incident survives Ledger reconstruction and suppresses a
  later completion event for the same incident.
- Approval events are suppressed inside the reminder window and delivered at
  the exact boundary.
- A delivered reminder appends a new exact v0.2 record for the same incident.
- Suppressed cycles complete successfully and release the Runner lock.

## Preserved boundaries

- `LIVE_NOTIFICATION` bypasses incident suppression and retains v0.1 writes.
- The Scheduler CLI still cannot activate LIVE mode.
- No Runner, Runtime, Ledger, approval, Executor or Production Queue behavior
  is changed by this Gate.
