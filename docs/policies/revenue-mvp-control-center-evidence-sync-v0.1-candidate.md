# Revenue MVP Control Center Evidence Sync v0.1 Candidate

This pure, read-only contract separates merged Revenue MVP evidence from facts
that still require current operational proof. It does not replace or relax the
existing Control Center checkpoint.

The merged 2026-09-16 lifecycle policy is recognized only for the reduced
surface. The reduced-surface mapping remains a review candidate; full and
expanded surfaces still require official confirmation. Merged offline
lifecycle filtering, artifact integration, launch rehearsal, lifecycle
receipts, and the inert bounded runner are version-bound. Builder prefiltering
and saved-receipt fail-closed behavior are tracked implementation evidence.

The current tracked checkout does not establish a current source DB SHA/public
artifact binding, a fresh read-only production D1 observation, or manual
reduced-surface Gate approval. The default synchronized result therefore stays
`CONTROL_CENTER_EVIDENCE_SYNCED_BLOCKED` with three explicit blockers and
selects source DB/public artifact revalidation as the next action. It does not
reuse untracked official-response files as evidence.
The blocked CLI result exits nonzero so automation cannot treat synchronization
as readiness.

Even when separately supplied evidence satisfies every synchronization field,
the strongest result is `CONTROL_CENTER_REDUCED_SURFACE_REVIEW_CANDIDATE`.
Publication, production activation, affiliate eligibility, and Gate mutation
remain false and require separate reviews.

The module performs no API call, network access, secret read, source DB read,
filesystem write, D1 operation, deployment, scheduler action, publication,
route activation, affiliate enablement, or Gate mutation. Missing, malformed,
unknown-version, wrong-scope, or contradictory evidence fails closed with a
specific blocker.
