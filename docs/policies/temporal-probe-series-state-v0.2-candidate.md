# Temporal Probe Series State v0.2 Candidate

This isolated pure contract adds an explicit `series_id` to temporal state
identity without modifying the active v0.1 runner, state store, or files.

- Series IDs are mandatory, bounded tokens; there is no implicit default.
- Comparisons require identical population and series identity.
- Cross-series comparison fails closed.
- Existing v0.1 documents remain explicitly readable as `LEGACY_READ_ONLY` but
  are never silently comparable with v0.2 candidates.
- Existing pseudonymous item-ID generation and comparison arithmetic are
  reused rather than reimplemented.

The candidate does not assign old states to a new series, reset history,
activate a fresh baseline, modify discovery, persist v0.2 documents, or connect
to the runner/orchestrator. Those require later isolated review and tests.

The contract performs no filesystem access, API request, database operation,
publication, deployment, D1 write, eligibility change, secret operation, or
affiliate activation.
