# Revenue MVP Current State v0.1

`scripts/revenue_mvp_current_state.py` is the current bounded Control Center
checkpoint after the one-time edge-verified activation on 2026-09-22.

It distinguishes two facts that older pre-publication checkpoints cannot
represent:

- the exact 100-item `UNORDERED_REDUCED_SURFACE` at `/items/` is live; and
- CTA, affiliate eligibility, D1 writes, scope expansion, and the global
  Publication Gate remain closed.

The repository-held edge receipt records the observed HTTP 200 response,
exact artifact SHA-256, `no-transform` cache directive, 100 articles, and the
absence of injected analytics, client-side item JavaScript, and affiliate
references. The checkpoint re-hashes the tracked artifact and independently
requires the affiliate runtime, route, and D1 evidence to remain inert.

Any missing, changed, malformed, or unexpectedly enabled evidence fails
closed. This checkpoint performs no network request, secret read, D1 access,
write, deployment, redirect, billing change, Gate mutation, or affiliate
activation. Its only successful next action is
`REVIEW_SEPARATE_AFFILIATE_CTA_GATE`.
