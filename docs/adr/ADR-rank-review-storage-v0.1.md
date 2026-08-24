# ADR: Rank / Review Future Storage Schema v0.1

- Status: Proposed; implementation not approved
- Decision date: 2026-08-25
- Policy version: 0.1
- Scope: Future production storage design for rank-sorted and review-sorted API query populations

## Context

The production collector currently collects only the date-sorted population.
The rank-sorted and review-sorted candidate policies remain disabled and have
`production_collection_eligible = false`.

The official definitions of the rank and review sort parameters have not been
confirmed. Temporal stability has been observed only through the Day 1
baseline. Day 2 and later turnover comparisons have not yet been evaluated.
No database migration or production integration has been approved.

A read-only audit of the current SQLite schema found that `item_snapshots`
already contains the main fields required to record an API observation:

- `observed_at`
- `collection_run_id`
- `source_sort`
- `source_offset`
- `source_position`
- `price_raw` and `price_min`
- `review_average` and `review_count`
- `query_context_json`

All current snapshots and collection runs use `source_sort = date`. The
existing database contains no production rank or review observations.

## Decision

Option B is the candidate design for a future promotion:

- Reuse `item_snapshots` for item-level observations.
- Add run-level metadata to `collection_runs` through an additive migration.
- Do not create a rank/review-specific snapshot table at this stage.

This decision records the preferred design direction only. It does not approve
implementation, migration, collector integration, or rank/review production
collection.

## Rationale

Option B is preferred because:

- It has lower migration risk than introducing a parallel observation model.
- The existing snapshot columns can represent sort, request offset, response
  position, price, and nullable review values.
- Existing item identity and snapshot foreign-key relationships can be reused.
- Run-level metadata can make query identity and collection intent explicit.
- It improves queryability without duplicating item observations.
- It provides clearer semantics while preserving the current date collector.
- An additive rollout can be disabled without dropping columns or rewriting
  existing date data.
- It offers the best current balance of collector complexity and long-term
  maintainability.

## Current schema deficiencies

The current schema does not yet provide all safeguards needed for production
rank/review collection:

- `source_sort` has no database `CHECK` constraint for allowed values.
- Requested offsets are not recorded at the collection-run level.
- Population-level status and completion are not represented.
- No explicit schema version is recorded.
- No collector policy version is recorded.
- No query identity version is recorded.
- The database does not enforce equality between snapshot and run
  `source_sort` values.
- Query identity is partially duplicated in `query_context_json`.
- There is no population-oriented index.
- There is no explicit migration ledger or active migration version.

The unique constraint on `item_snapshots` is currently:

`(collection_run_id, source_offset, source_position)`

This is sufficient only while one collection run is restricted to one
`source_sort`. Multiple sorts in the same run could use the same offset and
position and would conflict. A future collector must preserve the invariant
that one collection run represents one sort unless a later schema version
changes the key design.

## Candidate additive fields

The following `collection_runs` fields are candidates for a future migration:

- `schema_version`
- `collector_policy_version`
- `query_identity_version`
- `requested_offsets_json`
- `population_plan_hash`

Requirements for these fields:

- Prefer nullable additive columns for the initial migration.
- Backfill only values that can be recovered without inference.
- Never store credentials, tokens, request URLs, response bodies, or raw
  requests.
- Limit JSON to the smallest required structure, such as an array of numeric
  offsets.
- Validate JSON shape and element types in application and migration tests.
- Do not make `query_context_json` the authoritative source for fields that
  have normalized columns.

If future requirements need independent status for every requested population,
a later version may consider a normalized `collection_run_populations` child
table. That design is not selected or approved by this ADR.

## Population identity

A population identity consists of exactly:

1. `site`
2. `service`
3. `floor`
4. `source_sort`
5. `offset`
6. `hits`

The current schema can reconstruct this identity only by combining run-level
fields with snapshot-level `source_offset`. Future changes must preserve full
six-field isolation. Rank and review populations, and different offsets within
the same sort, must never be merged for analysis.

## Semantic contract

`source_position` means:

> The one-based observation position within one API query response.

It does not mean:

- global rank
- sales rank
- popularity rank
- market rank

The meaning of the rank and review sort parameters must not be stated more
specifically until confirmed by an official source. In particular, the review
sort must not be described as ordering by review average without confirmation.

Any query or downstream metric using `source_position` must retain the query
population context: site, service, floor, source sort, offset, and hits.

## Review fields

The existing nullable `review_average` and `review_count` fields can represent
numeric review observations returned for either query population. A missing
value remains `NULL`; it must not be replaced with zero. No unconfirmed range
or ordering semantics should be introduced.

## Temporal Probe separation

Temporal Probe state and production observations remain separate:

- Anonymous Temporal Probe state must not be inserted into the production
  database.
- Probe turnover metrics must not be inserted into `item_snapshots`.
- Probe state must not be mixed with production item observations.
- If aggregate persistence becomes necessary, it requires a separate table,
  policy version, and ADR.

The local Temporal Probe remains evidence for future eligibility decisions; it
is not production collection data.

## Preconditions for implementation

Migration and collector integration must not begin until all of the following
are satisfied:

1. The official sort definitions are confirmed.
2. Temporal stability is evaluated across multiple capture times.
3. Request cadence and rate-limit safety are confirmed.
4. Collection Policy is explicitly updated to make the intended population
   production-eligible.
5. This schema ADR, or a superseding version, is approved.
6. Fixture-only migration tests pass.
7. Backup and rollback procedures are reviewed and confirmed.

If any condition is missing, migration must not proceed.

## Migration principles

A future migration must follow these principles:

- Use additive migration only.
- Do not use destructive migration.
- Minimize changes to existing date data.
- Introduce an explicit schema version.
- Consider a migration ledger in addition to the SQLite schema version.
- Prefer rollback by disabling the new feature and collector path.
- Do not roll back by dropping columns.
- Back up and verify the database before and after migration.
- Do not infer backfill values that are not recoverable from validated data.

## Alternatives considered

### Option A: Use the current schema unchanged

Not selected because it leaves collection intent, requested offsets, policy
version, and query identity insufficiently explicit. It also depends too much
on repeated JSON context and application-only invariants. Migration risk is
lowest, but semantic clarity and long-term maintainability are inadequate.

### Option C: Add dedicated rank/review population and observation tables

Not selected at this stage because it duplicates existing snapshot capability
and creates greater migration, collector, query, rollback, and maintenance
complexity before the sort semantics and temporal behavior are confirmed.

Option C may be reconsidered in a later ADR if population-level lifecycle or
aggregate requirements cannot be represented safely with Option B.

## Consequences

Positive consequences:

- Existing item and snapshot storage remains the primary observation model.
- Date collection can remain isolated from unapproved rank/review work.
- Future metadata additions can be additive and versioned.
- Query identity becomes more explicit at the collection-run boundary.

Trade-offs:

- Some identity remains split across run and snapshot records.
- Requested offsets may initially require small, validated JSON metadata.
- Database constraints alone will not enforce every cross-table invariant
  without a later normalized population table.
- No production capability changes until all preconditions are satisfied.

## Non-goals

This ADR does not perform or approve:

- a migration or SQL schema change
- a collector change
- an API request
- rank/review database storage
- a Temporal Probe execution
- Temporal Probe state persistence in SQLite
- Public Data changes
- production deployment

## Validation basis

This ADR is based on the read-only schema audit of the current `items`,
`collection_runs`, and `item_snapshots` tables, their constraints, indexes,
foreign keys, existing aggregate distributions, and current collector write
contract. It intentionally does not assign unconfirmed API semantics.
