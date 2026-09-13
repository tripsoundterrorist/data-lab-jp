# Temporal Inert API Fetcher Candidate v0.1

This candidate prepares only the public portion of the four fixed FANZA video
ItemList request identities and reduces an already-supplied response to the
isolated collector bridge schema. It has no HTTP client, executable fetch
method, CLI, environment or credential loader, persistence, or scheduler.

The prepared request records the credential parameter *names* but never accepts
or renders credential values. Response reduction retains only `content_id` and
bounded request identity/count facts; titles, URLs, raw payloads, and error text
do not cross the boundary. HTTP 429 stops as `RATE_LIMIT`; other transport or
timeout failures reduce to `HTTP_ERROR`; malformed/API responses reduce to
`API_ERROR`. Retry authority remains zero in the downstream bridge.

The `rank` and `review` tokens remain observation labels only. Their official
meaning is unresolved and this candidate must not be used to publish ranking or
review claims. Live API use, credential access, state writes, scheduler changes,
production changes, deployment, publication, affiliate activation, D1 access,
and billing changes remain blocked. The next Gate is an isolated candidate
review; any later live execution still requires the official response and separate
explicit approval.
