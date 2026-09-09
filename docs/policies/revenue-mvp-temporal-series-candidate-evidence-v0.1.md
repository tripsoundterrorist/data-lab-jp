# Revenue MVP Temporal Series Candidate Evidence v0.1

`scripts/revenue_mvp_temporal_series_candidate_evidence.py` runs seven fixed,
memory-only checks across the isolated v0.2 candidate chain:

- series identity is explicit;
- cross-series comparison is rejected;
- legacy state remains readable but non-comparable;
- another series is excluded from discovery;
- an explicit baseline remains a dry-run plan;
- all four fixed populations can be assessed in order;
- the active v0.1 schema and runner remain unconnected.

Passing all checks creates implementation evidence only. The result always
reports `active_pipeline_connected=false`, `api_request_authorized=false`,
`state_write_authorized=false`, and `baseline_activation_authorized=false`.

The Gate does not modify the active schema, state store, runner, adapter,
orchestrator, scheduler, or saved states. It performs no filesystem access,
API request, database operation, publication, deployment, D1 write,
eligibility change, secret operation, or affiliate activation.
