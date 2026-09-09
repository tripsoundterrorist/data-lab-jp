# Revenue MVP Temporal Series Candidate Evidence v0.2

The evidence contract runs eight fixed memory-only checks. In addition to the
v0.1 series-boundary checks, it verifies that the isolated integration adapter:

- validates all four fixed sanitized payloads;
- creates explicit v0.2 states only in memory;
- reaches the existing dry orchestrator successfully;
- exposes aggregate output without series or content identifiers; and
- keeps API requests, state writes, baseline activation, and active-pipeline
  connection unauthorized.

Passing all checks remains implementation evidence only. It does not authorize
production integration, migration, collection, persistence, deployment, route
activation, affiliate eligibility, or publication.
