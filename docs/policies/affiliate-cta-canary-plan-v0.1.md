# Affiliate CTA Canary Plan v0.1

This is a review-only proposal for the shortest safe path from the live
100-item unordered reduced surface to an initial revenue measurement.

The first canary is capped at 10 separately validated items. Each item must use
the fixed label `公式商品ページを見る（外部サイト）`, a same-origin opaque
`/go/{public_id}` route, and the fixed visible PR disclosure in the same item
card immediately before the CTA. No ordering, rank, popularity, scarcity, or
urgency claim is introduced.

The minimum measurement set is CTA impressions, CTA clicks, redirect successes,
redirect blocks, and CTR. Any artifact mismatch, missing/non-proximate PR
disclosure, unverified affiliate eligibility, failed target/lifecycle
revalidation, duplicate/unattributable event, or excessive redirect error rate
stops the canary under a separately reviewed threshold.

`CTA_CANARY_READY_FOR_COMPLIANCE_REVIEW` means only that the plan can be sent to
COMPLIANCE. It does not enable a CTA, D1 row, redirect, deployment, paid plan,
or production write. Exact COMPLIANCE approval and a later explicit user
activation approval are both required.
