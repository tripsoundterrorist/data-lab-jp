# Revenue MVP Offline Lifecycle Filter v0.1 Candidate

Status: isolated memory-only integration. Production remains disabled.

This filter composes the confirmed lifecycle pure policy with the existing
`PublicationGateResult` before an item can become an offline artifact candidate.
It does not modify the Public Data builder or static-site renderer.

An item is an offline include candidate only when all three conditions hold:

1. lifecycle state is `ELIGIBILITY_CANDIDATE`;
2. freshness is explicitly confirmed; and
3. the exact existing Publication Gate result is internally consistent and all
   required gates are `PASS`.

Candidate lifecycle status alone is insufficient. API-unavailable,
affiliate-URL-absent/unknown, API-error, rate-limited, stale, unknown,
contradictory, or permissive inputs are removed from both artifact and CTA
candidacy. Preorder or out-of-stock signals do not exclude an otherwise valid
candidate.

The filter is mandatory for both index and detail candidates. Both field sets
are checked independently and explicitly reject `first_position`,
`source_position`, `source_offset`, `offset`, `rank`, `ranking`, and `top`.
The carried observation timestamp is taken only from the same lifecycle
decision's `observation_observed_at`; the adapter accepts no `generated_at`
substitute. If API order has changed, the API-order label is suppressed.

CTA candidacy additionally requires fixed evidence that the validated affiliate
URL belongs to the same item and same observation, PR disclosure is present,
and the Publication Gate passed. Missing or false CTA evidence leaves an
otherwise includable offline artifact candidate without CTA candidacy.

The result contains no item data and cannot emit ordinal/rank numbers,
`offset`, `first_position`, `source_position`, update-frequency, real-time, or
latestness claims. A confirmed observation timestamp may be carried only after
freshness validation; it is not a latestness claim.

Even the include result fixes `production_cta_allowed=false` and
`publication_allowed=false`. This Gate performs no build, filesystem/database
write, D1/API request, scheduler or route change, external send, deployment,
Publication Gate mutation, secret change, or production activation. Connecting
this decision to the dirty builder/static-site files requires a later,
conflict-free review.
