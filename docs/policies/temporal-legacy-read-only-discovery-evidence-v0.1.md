# Temporal Legacy Read-only Discovery Evidence v0.1

This memory-only Gate verifies the mixed-document discovery boundary:

- valid v0.1 documents remain readable;
- v0.1 documents are never accepted as v0.2 states or comparison candidates;
- v0.1 documents are counted and excluded from v0.2 discovery;
- cross-series v0.2 documents are also excluded; and
- only the latest earlier state from the current explicit series is selected.

A legacy-only history produces an explicit new-series baseline candidate, not a
legacy migration or comparison. Baseline activation remains a separate Gate.

The evidence authorizes no legacy conversion, history migration, filesystem or
D1 access, state write, API request, active pipeline connection, deployment,
route activation, publication, or affiliate eligibility change.
