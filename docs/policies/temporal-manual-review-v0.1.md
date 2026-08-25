# DATA LAB Temporal Day 4 Manual Review Criteria v0.1

## Boundary

This pure/read-only policy reviews safe aggregate observations for one fixed population at a time. `REVIEW_ELIGIBLE` means only that manual review may begin. It does not mean READY, PRODUCTION_READY, publishable, Publication/Lifecycle/Semantics Gate unlock, Official Blocker resolution, or production collection eligibility.

## Eligibility and inputs

An input is review-eligible only for rank/review at offset 1/101 with hits 100, `history_count >= 3`, at least three valid comparisons, 12–48 hour intervals, `OBSERVATION_ONLY`, `REVIEW_ELIGIBLE`, consistent counts/metrics, known bands, unique timestamps, and no anomaly. Each population is evaluated separately; averaging populations, combining rank/review, and an overall score are forbidden. Raw IDs, anonymous IDs, titles, URLs, states, paths, credentials, and exceptions are rejected.

## Consistency and outcomes

For v0.1, `max(retention_rate) - min(retention_rate) <= 0.20` is `ACCEPTABLE`; a larger range is `VARIABLE`. This threshold is an initial composition-observation threshold with no business meaning. Any change requires a new policy version.

Possible outcomes are `NOT_REVIEW_ELIGIBLE`, `CONTINUE_OBSERVATION`, `INTERNAL_CANDIDATE`, `HOLD_FOR_ANOMALY`, `HOLD_FOR_OFFICIAL_SEMANTICS`, `INSUFFICIENT_CONSISTENCY`, and `MANUAL_REVIEW_REQUIRED`. An acceptable valid series may be an `INTERNAL_CANDIDATE`; variable composition is `INSUFFICIENT_CONSISTENCY`. Malformed, inconsistent, duplicate, unknown, or contradictory input fails closed.

## Official and collection-policy separation

While `DMM_SORT_SEMANTICS` is pending, an internal candidate is only an internal technical observation candidate. Public interpretation and production promotion remain forbidden, and the result retains `official_semantics_status = PENDING`. Lifecycle status does not unlock or block this technical review and publication readiness is unaffected.

Rank/review `production_collection_eligible` remains false. `promotion_candidate = true` is only a proposal for later manual consideration. Collection Policy, Official Blocker Registry, and every Gate remain unchanged; any policy promotion requires a separate version, commit, and explicit approval.
