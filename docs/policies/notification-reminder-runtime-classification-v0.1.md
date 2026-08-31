# Notification Reminder Runtime Classification v0.1

Status: MOCK-only observability Gate.

## Contract

- A successfully delivered incident reminder in `MOCK_RUNTIME` adds the fixed
  reason code `INCIDENT_REMINDER_SELECTED` to the existing Runtime result.
- Runtime status and output fields remain unchanged.
- First or distinct deliveries do not receive the reminder classification.
- Suppressed reminders remain represented by the existing suppression result.

## Preserved boundaries

- `LIVE_NOTIFICATION` never receives this MOCK classification.
- Notification content, priority, adapter and sender inputs are unchanged.
- Reminder selection remains owned by Notification Noise Control and the
  Incident Suppression Coordinator.
- No Ledger, approval, Executor or Production Queue behavior changes.
