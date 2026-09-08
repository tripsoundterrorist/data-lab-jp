# DATA LAB Affiliate D1 Runtime Adapter Candidate v0.1

`runtime-candidates/affiliate-d1-runtime-adapter.mjs` is a non-deployed,
read-only candidate for `AFFILIATE_ITEM_LOOKUP`. It queries only
`affiliate_runtime_eligible_lookup`, binds one validated opaque public ID, and
invokes a trusted callback only for exactly one valid content ID.

Malformed input, missing capabilities, query failures, malformed rows, zero
rows, multiple rows, and exceptions never invoke the callback. Fixed safe
results contain no identifier, URL, credential, query error, or exception.
The two-row limit detects unexpected uniqueness violations fail-closed.

The callback is an internal boundary and must not log or expose its private
content ID. This candidate remains outside `functions/`, exports no Pages
handler, makes no DMM/FANZA request, emits no redirect, logs nothing, and writes
no D1 data.

Placement under `functions/`, provider connection, secrets, row enablement,
redirects, or deployment require later Gates. Issue #66 and all publication,
disclosure, rate-limit, rollback, and production-smoke gates remain closed.
