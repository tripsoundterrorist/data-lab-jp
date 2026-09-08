# Revenue MVP Temporal Continuation Assessment v0.1

`scripts/revenue_mvp_temporal_continuation_assessment.py` performs a read-only,
pre-API check of the latest valid state for each fixed rank/review population.
It preserves the existing 12–48 hour comparison interval without widening or
resetting it.

- Less than 12 hours returns `WAIT_FOR_OBSERVATION_WINDOW`.
- 12–48 hours returns `OBSERVATION_WINDOW_CANDIDATE` only.
- More than 48 hours returns `LONG_GAP_BLOCKED` and requires a separate fresh
  baseline policy.
- Missing populations, mixed windows, malformed timestamps, and internal
  errors fail closed.

No result authorizes an API request or state write. A window candidate still
requires the full operational preflight and separate execution authority. A
long gap does not authorize ignoring old states, overwriting history, treating
a new response as a baseline, or changing retention.

The assessment outputs only bounded counts, age ranges, and reason codes. It
does not expose item identifiers, titles, URLs, paths, credentials, response
payloads, or exceptions, and it performs no network request, database access,
publication, deployment, D1 write, eligibility change, or affiliate activation.
