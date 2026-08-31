# Notification Incident Suppression Coordinator v0.1

Status: pure decision Gate; no Runtime activation.

## Contract

- Validate the Ledger snapshot and retrieve only explicit v0.2 incident
  delivery evidence.
- Feed recognized evidence into Notification Noise Control v0.1.
- Empty and v0.1-only snapshots do not imply a prior incident delivery.
- Invalid identity, snapshot, timestamp, event type or contradictory evidence
  returns `COORDINATION_BLOCKED` with `delivery_allowed=false`.
- Reminder windows and critical-event behavior remain owned by Notification
  Noise Control.

## Preserved boundaries

- The Coordinator performs no I/O and does not mutate its input.
- It does not send notifications, read credentials or write the Ledger.
- It is not connected to MOCK_RUNTIME or LIVE_NOTIFICATION in this Gate.
- LIVE enablement, approval rules, Executor writes and Production Queue writes
  remain unchanged.
