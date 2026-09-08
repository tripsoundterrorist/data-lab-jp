# Revenue MVP Lifecycle Condition Evidence v0.1

`scripts/revenue_mvp_lifecycle_condition_evidence.py` executes five fixed,
read-only safety checks against the existing lifecycle contracts:

- stale non-observation is not treated as unavailable or publication-eligible;
- explicit unavailable verification is publication-ineligible;
- API non-return requires reverification and remains ineligible;
- API visibility is observation-only and remains ineligible;
- a confirmation boolean alone cannot activate unimplemented semantics.

Passing these checks creates implementation evidence only. The result always
reports `official_semantics_resolved=false` and
`publication_gate_unlock_allowed=false`. The separate official blocker for
zero-result meaning, availability distinctions, affiliate URL meaning, and
re-query guidance remains pending and cannot be inferred from these tests.

The Gate performs no network request, database access, persistence, collection,
publication, deployment, route or binding configuration, D1 write, eligibility
change, secret operation, or affiliate activation.
