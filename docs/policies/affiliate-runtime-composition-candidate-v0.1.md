# DATA LAB Affiliate Runtime Composition Candidate v0.1

`runtime-candidates/affiliate-runtime-composition.mjs` is a non-deployed
composition candidate. It first applies the existing Cloudflare route guards
and only then performs the existing read-only D1 eligible-view lookup. The
trusted pipeline callback is invoked only when every route fact is explicitly
true and exactly one eligible row exists.

The current production D1 state has no eligible rows, so this composition ends
with a fixed 404 result and never invokes the pipeline. Route rejection occurs
before any D1 query. Query errors and unexpected runtime errors fail closed
without returning identifiers, credentials, URLs, SQL details, or exceptions.

This artifact remains outside `functions/`; it exports no Pages handler, emits
no redirect or response body, performs no network request or D1 write, and
changes no route, binding, secret, row, or deployment configuration.

Moving it into `functions/`, supplying an HTTP response adapter, connecting the
DMM provider, enabling any row, or deploying requires later Gates. Issue #66,
publication eligibility, PR disclosure, rate limiting, lifecycle handling,
rollback, and production validation all remain mandatory and fail closed.
