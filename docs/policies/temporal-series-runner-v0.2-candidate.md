# Temporal Series Runner v0.2 Candidate

Status: isolated dry-run candidate; not connected to the active runner.

The candidate combines the existing same-series discovery and comparison
assessment with the memory-only v0.2 state-store write plan. The store plan is
created only after the assessment succeeds. A rejected baseline, comparison,
or store plan stops the chain fail-closed.

The result contains aggregate comparison fields and bounded statuses only. It
does not expose content IDs, series IDs, serialized state, filenames, or
digests.

This candidate performs and authorizes no API request, filesystem access,
state write, history migration, baseline activation, active-runner connection,
deployment, production route change, or affiliate eligibility change.
