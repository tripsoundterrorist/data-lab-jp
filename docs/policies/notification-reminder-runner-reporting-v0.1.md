# Notification Reminder Runner Reporting v0.1

Status: safe reporting Gate.

## Contract

- A completed Scheduled Runtime Runner cycle forwards the fixed Runtime reason
  `INCIDENT_REMINDER_SELECTED` when present.
- The existing `RUNTIME_CYCLE_COMPLETED` reason remains present.
- First deliveries, suppressed cycles and LIVE deliveries do not acquire the
  reminder classification unless Runtime explicitly supplied the fixed code.
- All other Runtime reason strings are excluded from successful Runner reports.

## Preserved boundaries

- Runner result fields, status and exit code are unchanged.
- No event payload, credential, transport response or arbitrary Runtime reason
  is exposed.
- No Runtime, notification delivery, LIVE, Ledger, approval, Executor or
  Production Queue behavior changes.
