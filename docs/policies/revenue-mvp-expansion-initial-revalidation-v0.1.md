# Revenue MVP Expansion Initial Revalidation v0.1

This is a bounded local transport for newly inserted expansion lookup rows. It
is separate from recurring lifecycle revalidation and accepts only an exact
private selection file outside the repository containing one to five opaque
public IDs. The selected D1 rows must still be disabled and in the original
pending rights, lifecycle, and verification state.

The default mode is read-only `DRY_RUN`. LIVE requires both `--execute` and the
exact confirmation token `LIVE_EXPANSION_INITIAL_REVALIDATION`. Each selected
item is queried once; there is no automatic retry. A single exact API result
with an allowlisted HTTPS affiliate URL writes the redirect target and audit
event before conditionally approving, resolving, and enabling that lookup row.
Missing, mismatched, malformed, or URL-absent results remain disabled. Upstream
errors remain pending and disabled for a separately approved bounded retry.

Output is aggregate-only. IDs, content IDs, URLs, credentials, response bodies,
SQL, and exceptions are not emitted. Temporary SQL is deleted after execution.
The operation does not alter the public artifact, Publication Gate, sitemap,
deployment, scheduler, or billing. Every LIVE batch requires separate explicit
approval and post-write aggregate verification.

`scripts/revenue_mvp_expansion_initial_selection.py` derives each selection
only from the immutable 178-row pre/post-write difference, orders opaque IDs
deterministically, and writes at most five IDs to an exclusive private file
outside the repository. Batch 0 was generated and then validated read-only
against production D1 on 2026-10-01. All five rows remained in their original
pending/disabled state. No provider API request or D1 write occurred. The
identifier-free receipt is stored at
`runtime/evidence/revenue-mvp-expansion-initial-batch-000-dry-run-20261001.json`.

The first explicitly approved LIVE attempt failed safe before any D1 write. A
post-failure read-only selection confirmed that all five rows remained pending
and disabled, and temporary SQL was absent. The original aggregate result did
not retain a reliable request count, so the number of provider requests is
recorded as unknown rather than inferred. No automatic retry was made. The
executor now retains an identifier-free failure stage and treats malformed
provider shapes as unconfirmed, not unavailable. Any retry is limited to one
separately approved attempt. Sanitized evidence is stored at
`runtime/evidence/revenue-mvp-expansion-initial-batch-000-live-attempt-20261001.json`.
