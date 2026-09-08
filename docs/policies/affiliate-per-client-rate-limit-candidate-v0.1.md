# DATA LAB Affiliate Per-Client Rate-Limit Candidate v0.1

This non-deployed adapter requires a precomputed opaque client key matching
`clt_` plus 64 lowercase hexadecimal characters and an exact public item ID.
It combines the actor and resource scopes only when calling the existing
Cloudflare Rate Limiting binding interface. Neither input is returned.

The adapter does not derive identity from an IP address, location, Request,
header, cookie, query parameter, or browser value. The trusted issuer and
lifecycle of the opaque key are intentionally not implemented or inferred.
Missing or malformed scope, missing binding, exceptions, and malformed binding
responses fail closed.

Cloudflare documents that Rate Limiting counters are location-local,
eventually consistent, and unsuitable for accurate accounting. This remains an
abuse-control layer rather than the only security boundary.

No binding/configuration, paid resource, handler, route, deployment, log, D1
write, eligibility, secret, or affiliate state is created or changed. The
deployment preflight `per_client_rate_limit` fact remains false until the key
issuer, numeric limits, binding configuration, privacy handling, and complete
runtime integration receive separate approval.
