# Temporal Isolated Collector Response Bridge v0.1 Candidate

The bridge can be constructed only through a fixture-only factory with injected
fetch and delay functions. It executes the four fixed rank/review identities in
order, with zero retries and at least one second between calls. Rate limiting or
any other accepted error stops remaining calls immediately.

Each fixture response must contain only the exact request identity, success,
result count, item content IDs, and a bounded error classification. Unknown or
additional fields are rejected. All four responses are buffered and validated
before one atomic state bundle is built; therefore a malformed fourth response
cannot produce partial state files.

Only the existing scope-approved isolated active-runner adapter may receive the
bundle. Results expose aggregate counts and fixed reason codes, not content IDs,
series IDs, paths, URLs, credentials, or response bodies. The bridge grants no
live API, scheduler, production-write, deploy, publication, affiliate, route,
D1, or billing authority. A live fetcher and scheduler require separate review
and explicit approval.
