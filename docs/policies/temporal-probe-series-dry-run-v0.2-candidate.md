# Temporal Probe Series Dry Run v0.2 Candidate

This pure candidate composes the isolated v0.2 series state and discovery
contracts with the existing temporal stability policy for one population.

- No same-series predecessor and `history_count=0` produces an explicit-series
  baseline plan only.
- A same-series predecessor requires positive history and is assessed through
  the existing comparison arithmetic and 12–48 hour stability policy.
- Long or short intervals, malformed discovery, and contradictory history fail
  closed.
- Results contain aggregate comparison metrics only, never state documents or
  identifiers.

Every result keeps API request, state write, and baseline activation
authorization false. The candidate is not connected to filesystem discovery,
the active runner, adapter, orchestrator, scheduler, or any live API.

This contract performs no filesystem access, API request, database operation,
publication, deployment, D1 write, eligibility change, secret operation, or
affiliate activation.
