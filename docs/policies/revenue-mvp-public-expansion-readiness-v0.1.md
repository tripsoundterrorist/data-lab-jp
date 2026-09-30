# Revenue MVP Public Expansion Readiness v0.1

The live Revenue MVP remains the exact existing 100-item surface. A larger local
database is not evidence that more products are safe or eligible to publish.
The next permitted planning stage is an isolated, exact 300-item candidate.

`scripts/revenue_mvp_public_expansion_readiness.py` is a pure fail-closed review
gate. It requires exact candidate coverage for eligibility, official images,
price, freshness, affiliate lookup and redirect behavior, and runtime
revalidation. It also requires proof that the existing surface is preserved,
canonical/sitemap and page quality review, Cloudflare Free capacity review, a
COMPLIANCE publication decision, a closed product-funnel measurement window,
and a tested rollback plan.

The current result is `BLOCKED`. Even complete evidence reaches only
`READY_FOR_MANUAL_EXPANSION_REVIEW`. It never writes Production or D1, deploys,
changes the Publication Gate, edits the sitemap, exposes new pages, or permits
affiliate/SNS claims. The existing production gates that require exactly 100
items remain intentional safeguards until a separately reviewed migration is
approved.

Expansion work is P1 behind P0 revenue measurement. If Cloudflare Free capacity
cannot be verified, work stops and any paid requirement must be reported before
the plan changes.
