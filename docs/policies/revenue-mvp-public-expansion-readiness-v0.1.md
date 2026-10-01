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

The read-only sitemap capacity review is now complete for the current URL
architecture. `sitemap.xml` contains nine unique first-party URLs, while the
item listing and item template remain `noindex,nofollow` and absent from the
sitemap. Expanding the existing listing from 100 to 300 records therefore adds
zero sitemap URLs and remains far below the 50,000-URL protocol limit. The
review is hash-bound to the four inspected source files and authorizes neither
sitemap changes nor publication. SEO content-quality review remains separate
and blocked. Aggregate evidence is recorded at
`runtime/evidence/revenue-mvp-expansion-sitemap-capacity-20261001.json`.

Expansion work is P1 behind P0 revenue measurement. If Cloudflare Free capacity
cannot be verified, work stops and any paid requirement must be reported before
the plan changes.

`scripts/revenue_mvp_public_expansion_coverage.py` is the preceding read-only
aggregate audit. It reports coverage counts and the gap to 300 without exposing
candidate identifiers or selecting products. A row is counted as base-eligible
only when its newest snapshot has a snapshot-bound title, official DMM image,
price, and validated affiliate lifecycle observation. Fresh coverage also
requires that snapshot to be no more than 48 hours old. Aggregate coverage does
not authorize an exact selection or publication.

The current date collection policy is two requests of 50 items (100 observations
per run). Reaching a 300-item observation window would require six requests at
the same page size. `scripts/revenue_mvp_expansion_collector_plan.py` records
that difference without calling the API or writing a database. The plan remains
blocked until a disposable database, backup/restore, request budget, rate-limit
safety, and overlap/duplicate validation are proven. The existing two-request
daily schedule must remain unchanged while this isolated plan is reviewed.

`scripts/revenue_mvp_expansion_page_validator.py` defines the isolated
pre-write page contract: exactly six 50-item pages at offsets 1, 51, 101, 151,
201, and 251, with exactly 300 unique non-empty content IDs. Any short page,
offset drift, malformed identifier, or duplicate across pages blocks database
writes. This validator is not connected to the live collector in v0.1.

`scripts/revenue_mvp_expansion_disposable_db_rehearsal.py` verifies the database
isolation boundary without an API request. It creates a temporary SQLite backup,
restores that copy into a second temporary database, compares logical table
digests and counts, verifies integrity and foreign keys, confirms the source
file identity did not change, and removes both temporary files automatically.
An active native collection run blocks the rehearsal.

The 2026-10-01 rehearsal against database SHA-256
`cd24816b185234d4a3e05e180f3e95ca97ab3b6c98cdf105da47b8ffaf7ecb53`
verified 5 tables, 1,109 items, 5,244 snapshots, and 55 collection runs. No
temporary files were retained and the source identity was unchanged. This
evidence satisfies only the isolated database and backup/restore prerequisites;
it does not approve an API request or collection run.

`scripts/revenue_mvp_expansion_collector_safety_audit.py` statically verifies
the existing collector source without importing it or loading credentials. It
requires at least one second between requests, a bounded timeout, immediate
failure on HTTP/network errors, no retry marker, and response validation before
the database-write phase. Passing this audit confirms the reusable stop and
spacing behavior only; the expanded six-request budget remains separately
blocked.

`scripts/revenue_mvp_expansion_isolated_collection.py` is the only approved
harness for a one-time six-request test. It opens the source only to create a
temporary SQLite backup, points the existing collector at that disposable
database, suppresses collector output, validates the exact six-page contract,
reports aggregate coverage only, verifies the source file identity, and removes
the temporary database. It never publishes or changes the production schedule.

The explicitly approved 2026-10-01 isolated run completed six API requests,
fetched six pages and 300 items, found zero duplicate content IDs, and passed
the exact page contract. All 300 newest candidate rows met the base title,
official-image, price, and affiliate-observation checks. The production source
database remained at SHA-256
`cd24816b185234d4a3e05e180f3e95ca97ab3b6c98cdf105da47b8ffaf7ecb53`
and the disposable database was removed. Its freshness count is not accepted:
the supplied evaluation timestamp preceded snapshots created during the run,
causing a negative-age rejection. The harness now evaluates freshness after
collection completion. No second API run was performed for this correction.

`date_expansion_candidate_policy()` now records the proven request shape as an
explicitly manual, disabled, experimental, non-publication policy: six 50-item
requests at fixed offsets with one-second spacing, stop-on-error, and zero
retries. It is valid only for an isolated candidate run and is deliberately not
production-collection eligible. The active daily date policy remains two
requests and 100 observations.

`scripts/revenue_mvp_expansion_storage_gate.py` defines the next collection-only
retention boundary. A candidate database must remain below the Git-ignored
`runtime/private/` root, be distinct from the production database, contain no
raw payload or sensitive-name columns, and end in one verified six-page,
300-item run. Retention is limited to seven validated generations. The gate
forbids publication, sitemap, and D1 connections and never exposes candidate
identifiers.

`scripts/revenue_mvp_expansion_storage_commit.py` provides the gated atomic
commit step. It accepts only a hash-pinned staged database already inside the
private root, re-runs the storage gate, backs up an existing collection-only
primary before replacement, atomically moves the candidate into place, verifies
the retained identity, and rotates only its dedicated backup directory to seven
generations. It never writes the production database or authorizes publication.

The isolated collector accepts `--retain-collection-only` as an explicit opt-in.
Without it, the disposable database is always deleted. With it, the harness
accepts only the repository's Git-ignored `runtime/private/` root, copies the
fully validated disposable database to a random staged file, invokes the atomic
storage commit, and removes any uncommitted stage in `finally`. A retention
failure blocks the run receipt and never falls back to publication or the
production database.

The explicitly approved retained run completed at 2026-09-30T18:52:43Z. It
fetched 300 items in six requests with zero duplicates; all 300 passed the base
and 48-hour freshness coverage checks. The private collection-only database now
contains 1,287 items and 5,544 snapshots at SHA-256
`6d1ea77411d1aa631c807ad4f76394e7aa00a3af0abdd20c920af75119d9a042`.
The production source remained unchanged, and publication, sitemap, D1, and the
daily production schedule were not modified. Aggregate evidence is recorded in
`runtime/evidence/revenue-mvp-expansion-collection-20261001.json`; the database
itself remains Git-ignored.

The public-expansion readiness gate consumes only that committed aggregate
evidence. It now recognizes exact 300-item candidate, eligibility, official
image, price, freshness, and existing-surface-preservation coverage. Missing,
malformed, or contradictory evidence falls back to zero verified items. D1
lookup/redirect/runtime coverage and every SEO, capacity, COMPLIANCE, funnel,
and rollback decision remain blocked independently.

`scripts/export_revenue_mvp_expansion_lookup_candidate.py` exports only the
newest verified six-page run, not every item accumulated in the private
database. It requires exactly 300 unique in-scope identifiers, reuses the page
validator, pins the source database SHA-256, and writes an atomic private SQL
candidate whose rows inherit disabled and pending D1 defaults. Export does not
import D1, create redirect targets, enable affiliate rows, or authorize
publication.

The 2026-10-01 export produced and independently validated 300 disabled lookup
rows at candidate SHA-256
`d77105c1d0d81e2b79135b42c5163f1d722b55ad9806324b15ce2f3da1390434`.
Runtime-eligible rows, redirect targets, and runtime revalidations remain zero.
The SQL stays Git-ignored; only aggregate evidence is committed at
`runtime/evidence/revenue-mvp-expansion-lookup-20261001.json`.

`scripts/revenue_mvp_expansion_d1_overlap_audit.py` loads a hash-pinned private
D1 SQL snapshot into in-memory SQLite and compares only aggregate mapping,
eligibility, redirect, and runtime coverage against the exact 300-row candidate.
It emits no identifiers or URLs and performs no persistent or D1 write. Missing
rows and mapping conflicts remain separate fail-closed findings.

The 2026-10-01 aggregate audit found 122 exact lookup matches and 178 missing
rows among the 300-item candidate, with zero mapping conflicts. Existing private
D1 evidence contained redirect targets for 119 candidate items and complete
runtime coverage for 99. The safe next artifact is therefore an insert-only,
disabled 178-row delta; replacing or deleting the other 987 remote mappings is
not permitted. Aggregate evidence is recorded at
`runtime/evidence/revenue-mvp-expansion-d1-overlap-20261001.json`.

`scripts/revenue_mvp_expansion_d1_delta.py` now produces that exact scoped delta
only from hash-pinned inputs. Its in-memory preflight preserves all 1,109
existing rows, adds exactly 178 default-disabled and pending rows, reaches 1,287
rows, and leaves runtime eligibility unchanged. The generated SQL remains in
Git-ignored private storage and has not been applied to D1. Its aggregate
receipt is recorded at
`runtime/evidence/revenue-mvp-expansion-d1-delta-20261001.json`. A separate
approval and final remote-identity recheck are required before any D1 write.

`scripts/revenue_mvp_expansion_d1_prewrite_gate.py` defines that final recheck.
It accepts only a hash-pinned remote export no more than 15 minutes old, rebuilds
the scoped delta, requires byte-exact equality with the reviewed private delta,
and rechecks the 1,109 + 178 = 1,287 row postcondition in memory. Stale exports,
mapping changes, count changes, identity changes, or a non-exact delta block the
operation. Passing this gate is review readiness only; it does not authorize or
perform the D1 write or publication.

After explicit operator approval on 2026-10-01, the hash-pinned 178-row delta
was applied once to production D1. A fresh post-write export was compared with
the immutable pre-write export by
`scripts/revenue_mvp_expansion_d1_postwrite_verify.py`. The verifier confirmed
that all 1,109 existing rows were unchanged, the final count was 1,287, and the
178 new mappings were exactly the candidate gap and remained disabled/pending.
Eligibility, redirect-target, and runtime-redirect counts were unchanged. This
does not authorize publication or enable any new CTA. Sanitized evidence is at
`runtime/evidence/revenue-mvp-expansion-d1-postwrite-20261001.json`.

The post-write candidate-scoped audit records exact lookup coverage for all 300
items, 119 stored redirect targets, and 69 currently runtime-eligible redirects.
The readiness gate consumes these aggregate values fail-closed. Lookup coverage
is therefore complete, but redirect and fresh runtime coverage remain blocking;
stored targets must not be treated as eligible when revalidation has disabled
their lookup rows.

`scripts/revenue_mvp_expansion_activation_batch_plan.py` compares the immutable
pre/post-write exports and separates the 300-item candidate into 178 newly
inserted initial-validation rows, 50 pre-existing upstream-unconfirmed retry
rows, 69 currently active rows, and 3 legacy pending rows requiring separate
review. Initial validation and retry are never mixed. Any future execution is
capped at five items per batch, with at most one retry after a bounded wait of
no more than 300 seconds. The plan performs no API request or D1 write and does
not grant activation. Aggregate evidence is recorded at
`runtime/evidence/revenue-mvp-expansion-activation-batch-plan-20261001.json`.
