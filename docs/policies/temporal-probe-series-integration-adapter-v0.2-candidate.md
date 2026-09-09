# Temporal Probe Series Integration Adapter v0.2 Candidate

Status: isolated implementation candidate; not connected to an active pipeline.

This adapter is the narrow boundary between four already-sanitized population
payloads and the existing temporal series dry-run orchestrator. It validates the
entire fixed population set before creating any v0.2 state in memory.

## Fail-closed boundary

- The population order and identity must exactly match `FIXED_POPULATIONS`.
- Every payload and item must contain only the documented fields.
- `result_count` must equal the item count and must not exceed `hits`.
- Empty or duplicate content IDs block the complete integration attempt.
- Output contains aggregate assessment data only, never series or content IDs.
- Downstream rejection is preserved as a blocked result.

## Explicit non-authorizations

The candidate performs no HTTP request, filesystem access, D1 access, state
write, baseline activation, publication, deployment, or production route
activation. It does not connect to the active adapter or runner. A separate Gate
and review are required before any such connection.
