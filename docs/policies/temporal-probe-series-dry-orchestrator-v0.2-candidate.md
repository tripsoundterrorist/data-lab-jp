# Temporal Probe Series Dry Orchestrator v0.2 Candidate

This pure candidate evaluates exactly the four fixed rank/review populations
in runbook order using the isolated series dry-run contract.

- Inputs must contain all four current states, document groups, and history
  counts with exact fixed identities.
- Every current state must match its ordered population.
- Evaluation stops after the first blocked population; remaining populations
  are explicitly `NOT_RUN`.
- A complete result means only that four memory-only plans or assessments were
  produced. It is not collection, baseline, or publication readiness.
- Safe output contains aggregate status and metrics only, never series or item
  identifiers or state documents.

API request, state write, and baseline activation authorization are always
false. The candidate is not connected to filesystem discovery, the active
runner, adapter, orchestrator, scheduler, or any live API.

This contract performs no filesystem access, API request, database operation,
publication, deployment, D1 write, eligibility change, secret operation, or
affiliate activation.
