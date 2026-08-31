# Notification Ledger v0.2 MOCK Runtime Integration

Status: small Gate, default production behavior unchanged.

## Contract

- `MOCK_RUNTIME` records successful deliveries through the explicit
  `record_success_v02` API.
- The v0.2 record contains the existing exact event identity and the stable
  incident identity derived from the already validated event.
- An unavailable incident identity fails closed with
  `LEDGER_INCIDENT_IDENTITY_INVALID`; no ledger record is committed.
- `LIVE_NOTIFICATION` continues to use the existing v0.1 writer.
- `DRY_RUN` remains read-only.

## Preserved boundaries

- Delivery selection, transport behavior and persistent exact-event
  deduplication are unchanged.
- This Gate does not activate incident-level suppression or notification noise
  policy.
- No existing record is migrated or rewritten.
- LIVE enablement, approval rules, Executor writes and Production Queue writes
  are outside this Gate.
