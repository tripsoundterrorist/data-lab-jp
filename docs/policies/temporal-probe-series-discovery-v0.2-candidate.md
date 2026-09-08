# Temporal Probe Series Discovery v0.2 Candidate

This pure, filesystem-independent candidate selects comparison history only
when population identity and explicit `series_id` both match.

- The latest earlier same-series state is the only comparison candidate.
- Legacy v0.1 states remain readable but are excluded from v0.2 comparison.
- States from another explicit series are counted and excluded.
- No same-series predecessor yields `EXPLICIT_BASELINE_CANDIDATE`; this is a
  classification, not authorization to collect or persist a baseline.
- Duplicate timestamps, same-series equal/future timestamps, malformed input,
  and unreadable documents fail closed.

The safe result exposes only bounded counts and reason codes. It never exposes
state contents or identifiers. The candidate is not connected to directory
discovery, the state store, runner, adapter, or orchestrator and performs no
filesystem access, API request, database operation, publication, deployment,
D1 write, eligibility change, secret operation, or affiliate activation.
