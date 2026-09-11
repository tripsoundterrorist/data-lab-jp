# Affiliate Client Key Derivation Candidate v0.1

`runtime-candidates/affiliate-client-key-derivation.mjs` is an isolated,
non-deployed privacy boundary for a future Cloudflare affiliate route.

It accepts only a Worker `Request` and a server-side secret of at least 32
characters. It consumes Cloudflare's `CF-Connecting-IP` value inside the
boundary and returns only a domain-separated HMAC-SHA-256 opaque key. Raw IP,
header values, the secret, request URL, and exception details are never returned,
logged, or persisted. Missing, duplicated/comma-joined, malformed, or oversized
addresses and unavailable Web Crypto fail closed.

The candidate does not configure a secret, Rate Limiting binding, route, Pages
Function, D1, logging, API call, redirect, deployment, or publication. Secret
binding creation and key rotation require separate review. This candidate does
not authorize production use or a paid Cloudflare plan.
