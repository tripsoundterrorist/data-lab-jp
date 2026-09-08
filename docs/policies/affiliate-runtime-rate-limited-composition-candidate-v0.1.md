# DATA LAB Affiliate Runtime Rate-Limited Composition Candidate v0.1

This non-deployed composition orders existing fail-closed boundaries as:

1. validate the exact GET/HEAD route and all existing activation facts;
2. call the coarse, resource-scoped Rate Limiting binding adapter;
3. only when allowed, perform the existing read-only eligible D1 lookup;
4. only for exactly one eligible row, invoke the existing pipeline callback.

Invalid routes do not call the rate limiter or D1. A missing binding, malformed
rate-limit response, or exception returns a fixed 404 and does not query D1. An
exceeded limit returns a fixed 429 and does not query D1. Private identifiers,
keys, provider data, and exception details are not returned or logged.

This candidate does not implement a per-client limit and does not satisfy the
deployment preflight rate-limit Gate. Cloudflare's location-local, eventually
consistent limiter is coarse upstream protection only, not accounting or the
only abuse-control boundary.

There is no Pages handler, binding/config addition, deployment, route activation,
redirect emitter, D1 write, eligibility change, secret change, or affiliate
enablement. Production integration remains blocked on all existing Gates.
