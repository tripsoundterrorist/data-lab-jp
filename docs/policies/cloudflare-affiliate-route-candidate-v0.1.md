# DATA LAB Cloudflare Affiliate Route Candidate v0.1

## Decision

The lowest-complexity production target is a Cloudflare Pages Function with
D1 for private item lookup and secret bindings for DMM credentials. The current
Python/SQLite implementation remains the policy and offline reference; the
Cloudflare runtime requires a JavaScript-compatible adapter.

## Current artifact

`runtime-candidates/cloudflare-affiliate-route.mjs` is deliberately outside the
reserved `functions/` directory. It exports no Pages `onRequest` handler and has
no Wrangler configuration, binding IDs, secret values, network call, database
query, redirect emitter, or deployment path.

The candidate validates only:

- exact GET/HEAD route shape;
- absence of query and fragment;
- explicit boolean activation facts;
- required binding capabilities without returning their values;
- rate-limit approval before other activation facts;
- fixed bodyless, no-store response metadata.

All safe results omit the public ID, request URL, credential values, affiliate
URL, DMM response, and redirect location.

## Cost boundary

At the recorded Revenue MVP scale (approximately 1.5 MB and 750 items), the
candidate data size is below Cloudflare D1's documented Workers Free storage
allowance. No D1 database or paid resource is created by this change. Actual
usage and billing must be rechecked before activation.

## Activation boundary

Moving code under `functions/`, creating D1, importing data, adding bindings or
secrets, or deploying a preview/production handler requires a separate approval.
Issue #66 and every publication and production gate remain fail-closed.
