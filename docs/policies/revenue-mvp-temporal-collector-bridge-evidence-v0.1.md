# Revenue MVP Temporal Collector Bridge Evidence v0.1

This evidence Gate executes the isolated collector bridge with local fixture
functions and caller-owned temporary directories only. It verifies the fixed
four-population order, three one-second delay calls, atomic four-response
validation, four isolated state files, aggregate-only results, and stop-on-rate-
limit behavior with no retry or partial state write.

The Gate loads no credentials and performs no live API request. All scheduler,
production-write, deploy, publication, affiliate, route, D1, and billing
authority remains false. Missing, changed, permissive, or failing evidence is
blocked with fixed reason codes.

A passing result advances only to
`REVIEW_LIVE_TEMPORAL_API_FETCHER_CONTRACT`. It does not authorize a live
fetcher, an API request, or scheduler integration.
