# Revenue MVP Reduced-Surface Gate Mapping v0.1 Candidate

Status: read-only mapping review candidate. No Gate is changed.

This contract binds the exact versions merged through PRs #242–#246 to a
separate `REDUCED_SURFACE` review. It validates the official lifecycle policy,
reduced-surface semantics contract, offline lifecycle filter, offline artifact
integration, and offline launch rehearsal as five mandatory evidence layers.
Missing, false, unknown, malformed, or version-mismatched evidence fails closed.

The reduced-surface required semantics cover API-unavailable and affiliate-URL
exclusion, bounded error/rate-limit/stale handling, preorder/stock behavior,
API-order label suppression, same-observation timestamp provenance, CTA
same-item/same-observation/PR/Gate requirements, atomic index/detail filtering,
and offline rollback.

Ordinal public rank, provider update behavior, and internal history retention
are explicitly `OUT_OF_SCOPE_FOR_REDUCED_SURFACE`; they are never mapped to
`RESOLVED`. Full and expanded surfaces remain
`PENDING_OFFICIAL_CONFIRMATION`. Existing Official Blocker Registry records and
Publication Readiness input are inspected but never overwritten.

All outcomes fix `publication_status=CLOSED`, `gate_mutation_allowed=false`,
`production_allowed=false`, and `affiliate_allowed=false`. A successful result
is only `REDUCED_SURFACE_REVIEW_CANDIDATE` and requires a later manual Gate
review. This module performs no API/D1/builder call, filesystem write, deploy,
route or scheduler change, secret operation, publication, or Gate mutation.
