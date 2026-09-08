# Revenue MVP Sort Condition Evidence v0.1

`scripts/revenue_mvp_sort_condition_evidence.py` executes six fixed, read-only
safety checks against the existing collection and official-blocker contracts:

- rank and review candidates remain experimental, disabled, and production-ineligible;
- a global popularity-rank interpretation is rejected;
- a review-average ordering interpretation is rejected;
- even mechanically complete eligibility booleans cannot promote v0.1 candidates;
- the official sort blocker remains pending and cannot unlock its Gate.

Passing these checks creates implementation evidence only. The result always
reports `official_semantics_resolved=false` and
`publication_gate_unlock_allowed=false`. It does not define `sort=rank` or
`sort=review`, interpret offset or query position, permit a public rank claim,
or infer temporal update behavior.

The Gate performs no API request, collection, database access, persistence,
publication, deployment, route or binding configuration, D1 write, eligibility
change, secret operation, or affiliate activation.
