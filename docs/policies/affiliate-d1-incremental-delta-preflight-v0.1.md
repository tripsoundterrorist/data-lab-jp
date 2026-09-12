# Affiliate D1 Incremental Delta Preflight v0.1

This preflight recomputes the exact insert-only delta from immutable remote and
candidate snapshots, requires byte-for-byte equality with the supplied delta,
and applies it only to isolated in-memory SQLite using the candidate schema.

Success requires the remote count, delta count, and final count to agree; every
row must retain pending rights, pending lifecycle, pending verification, and
`affiliate_enabled=0`; and the runtime-eligible view must remain empty. Identity
or byte drift, a non-insert-only delta, schema drift, duplicate mapping, changed
defaults, or any failed postcondition returns `FAIL_CLOSED`.

The result exposes aggregate counts and booleans only. It performs no production
D1 write, network request, deployment, route activation, affiliate enablement,
publication, or paid-plan change. A successful result requires a separate
explicit approval before applying the delta to production D1.
