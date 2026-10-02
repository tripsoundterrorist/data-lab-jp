# Revenue MVP Expansion Initial Revalidation v0.1

This is a bounded local transport for newly inserted expansion lookup rows. It
is separate from recurring lifecycle revalidation and accepts only an exact
private selection file outside the repository containing one to five opaque
public IDs. The selected D1 rows must still be disabled and in the original
pending rights, lifecycle, and verification state.

The default mode is read-only `DRY_RUN`. LIVE requires both `--execute` and the
exact confirmation token `LIVE_EXPANSION_INITIAL_REVALIDATION`. Each selected
item is queried once; there is no automatic retry. A single exact API result
with an allowlisted HTTPS affiliate URL writes the redirect target and audit
event before conditionally approving, resolving, and enabling that lookup row.
Missing, mismatched, malformed, or URL-absent results remain disabled. Upstream
errors remain pending and disabled for a separately approved bounded retry.

Output is aggregate-only. IDs, content IDs, URLs, credentials, response bodies,
SQL, and exceptions are not emitted. Temporary SQL is deleted after execution.
The operation does not alter the public artifact, Publication Gate, sitemap,
deployment, scheduler, or billing. Every LIVE batch requires separate explicit
approval and post-write aggregate verification.

`scripts/revenue_mvp_expansion_initial_selection.py` derives each selection
only from the immutable 178-row pre/post-write difference, orders opaque IDs
deterministically, and writes at most five IDs to an exclusive private file
outside the repository. Batch 0 was generated and then validated read-only
against production D1 on 2026-10-01. All five rows remained in their original
pending/disabled state. No provider API request or D1 write occurred. The
identifier-free receipt is stored at
`runtime/evidence/revenue-mvp-expansion-initial-batch-000-dry-run-20261001.json`.

The first explicitly approved LIVE attempt failed safe before any D1 write. A
post-failure read-only selection confirmed that all five rows remained pending
and disabled, and temporary SQL was absent. The original aggregate result did
not retain a reliable request count, so the number of provider requests is
recorded as unknown rather than inferred. No automatic retry was made. The
executor now retains an identifier-free failure stage and treats malformed
provider shapes as unconfirmed, not unavailable. Any retry is limited to one
separately approved attempt. Sanitized evidence is stored at
`runtime/evidence/revenue-mvp-expansion-initial-batch-000-live-attempt-20261001.json`.

After the separately approved single retry, all five selected rows passed exact
official API and affiliate URL validation and were conditionally approved and
enabled. Five redirect targets were added. A concurrent recurring revalidation
changed 25 other rows from pass/enabled to upstream-unconfirmed pending/disabled;
those fail-closed changes were not reversed. The resulting candidate coverage
was 300 lookup rows, 124 stored targets, and 49 runtime-eligible redirects.
Publication and automatic additional batches remain unauthorized. Evidence is
stored at
`runtime/evidence/revenue-mvp-expansion-initial-batch-000-live-success-20261001.json`.

Later lifecycle revalidation can make a historical fixed batch stale. The
selection builder therefore accepts an optional current D1 snapshot. In that
mode it verifies all 178 inserted mappings and allowlisted lifecycle states,
excludes rows that are already active or awaiting retry, and selects only rows
still in the original pending/disabled state. Mapping drift, an unknown state,
or a mixed stale selection blocks before provider API access or D1 writes.

On 2026-10-02, the current-state selection excluded already active rows and
produced a five-item private batch from 155 remaining pending rows. A remote D1
read-only dry run verified all five were still pending and disabled. It made no
provider API request or D1 write and did not grant LIVE execution. Aggregate
evidence is stored at
`runtime/evidence/revenue-mvp-expansion-current-pending-batch-000-dry-run-20261002.json`.

After separate explicit approval, the same hash-pinned five-item selection was
executed once. All five exact official API responses contained allowlisted
affiliate URLs, and the bounded D1 write completed. Post-write aggregate review
recorded 127 active runtime redirects, 147 stored targets, and 150 untouched
initial-validation rows. The public artifact remains 100 items and no deployment
or Publication Gate change occurred. Additional LIVE batches remain prohibited
without a new current-state selection, dry run, and explicit approval. Evidence
is stored at
`runtime/evidence/revenue-mvp-expansion-current-pending-batch-000-live-success-20261002.json`.

A second separately approved current-state batch also completed five of five
exact official API validations. Post-write aggregate review recorded 132 active
runtime redirects, 152 stored targets, and 145 untouched initial-validation
rows. The public artifact remains 100 items. Evidence is stored at
`runtime/evidence/revenue-mvp-expansion-current-pending-batch-001-live-success-20261002.json`.

A third separately approved current-state batch completed five of five exact
official API validations. Post-write aggregate review recorded 137 active
runtime redirects, 157 stored targets, and 140 untouched initial-validation
rows. The public artifact remains 100 items. Evidence is stored at
`runtime/evidence/revenue-mvp-expansion-current-pending-batch-002-live-success-20261002.json`.

A fourth separately approved current-state batch completed five of five exact
official API validations. Post-write aggregate review recorded 142 active
runtime redirects, 162 stored targets, and 135 untouched initial-validation
rows. The public artifact remains 100 items. Evidence is stored at
`runtime/evidence/revenue-mvp-expansion-current-pending-batch-003-live-success-20261002.json`.

A fifth separately approved current-state batch completed five of five exact
official API validations. Post-write aggregate review recorded 147 active
runtime redirects, 167 stored targets, and 130 untouched initial-validation
rows. The public artifact remains 100 items. Evidence is stored at
`runtime/evidence/revenue-mvp-expansion-current-pending-batch-004-live-success-20261002.json`.

A sixth separately approved current-state batch completed five of five exact
official API validations. Post-write aggregate review recorded 152 active
runtime redirects, 172 stored targets, and 125 untouched initial-validation
rows. The public artifact remains 100 items. Evidence is stored at
`runtime/evidence/revenue-mvp-expansion-current-pending-batch-005-live-success-20261002.json`.

A seventh separately approved current-state batch completed five of five exact
official API validations. Post-write aggregate review recorded 157 active
runtime redirects, 177 stored targets, and 120 untouched initial-validation
rows. The public artifact remains 100 items. Evidence is stored at
`runtime/evidence/revenue-mvp-expansion-current-pending-batch-006-live-success-20261002.json`.

An eighth separately approved current-state batch completed five of five exact
official API validations. Post-write aggregate review recorded 162 active
runtime redirects, 182 stored targets, and 115 untouched initial-validation
rows. The public artifact remains 100 items. Evidence is stored at
`runtime/evidence/revenue-mvp-expansion-current-pending-batch-007-live-success-20261002.json`.

A ninth separately approved current-state batch completed five of five exact
official API validations. Post-write aggregate review recorded 167 active
runtime redirects, 187 stored targets, and 110 untouched initial-validation
rows. The public artifact remains 100 items. Evidence is stored at
`runtime/evidence/revenue-mvp-expansion-current-pending-batch-008-live-success-20261002.json`.

A tenth separately approved current-state batch completed five of five exact
official API validations. Post-write aggregate review recorded 172 active
runtime redirects, 192 stored targets, and 105 untouched initial-validation
rows. The public artifact remains 100 items. Evidence is stored at
`runtime/evidence/revenue-mvp-expansion-current-pending-batch-009-live-success-20261002.json`.

An eleventh separately approved current-state batch completed five of five exact
official API validations. Post-write aggregate review recorded 177 active
runtime redirects, 197 stored targets, and 100 untouched initial-validation
rows. The public artifact remains 100 items. Evidence is stored at
`runtime/evidence/revenue-mvp-expansion-current-pending-batch-010-live-success-20261002.json`.

A twelfth separately approved current-state batch completed five of five exact
official API validations. Post-write aggregate review recorded 182 active
runtime redirects, 202 stored targets, and 95 untouched initial-validation
rows. The public artifact remains 100 items. Evidence is stored at
`runtime/evidence/revenue-mvp-expansion-current-pending-batch-011-live-success-20261002.json`.

A thirteenth separately approved current-state batch completed five of five
exact official API validations. Post-write aggregate review recorded 187 active
runtime redirects, 207 stored targets, and 90 untouched initial-validation
rows. The public artifact remains 100 items. Evidence is stored at
`runtime/evidence/revenue-mvp-expansion-current-pending-batch-012-live-success-20261002.json`.

A fourteenth separately approved current-state batch completed five of five
exact official API validations. Post-write aggregate review recorded 192 active
runtime redirects, 212 stored targets, and 85 untouched initial-validation
rows. The public artifact remains 100 items. Evidence is stored at
`runtime/evidence/revenue-mvp-expansion-current-pending-batch-013-live-success-20261002.json`.

A fifteenth separately approved current-state batch completed five of five
exact official API validations. Post-write aggregate review recorded 197 active
runtime redirects, 217 stored targets, and 80 untouched initial-validation
rows. The public artifact remains 100 items. Evidence is stored at
`runtime/evidence/revenue-mvp-expansion-current-pending-batch-014-live-success-20261002.json`.

A sixteenth separately approved current-state batch completed five of five
exact official API validations. Post-write aggregate review recorded 202 active
runtime redirects, 222 stored targets, and 75 untouched initial-validation
rows. The public artifact remains 100 items. Evidence is stored at
`runtime/evidence/revenue-mvp-expansion-current-pending-batch-015-live-success-20261002.json`.

A seventeenth separately approved current-state batch completed five of five
exact official API validations. Post-write aggregate review recorded 207 active
runtime redirects, 227 stored targets, and 70 untouched initial-validation
rows. The public artifact remains 100 items. Evidence is stored at
`runtime/evidence/revenue-mvp-expansion-current-pending-batch-016-live-success-20261002.json`.

An eighteenth separately approved current-state batch completed five of five
exact official API validations. The LIVE command output was not captured, so it
was not retried; a post-write D1 snapshot confirmed exactly five new active
rows, 212 active runtime redirects, 232 stored targets, and 65 untouched
initial-validation rows. The public artifact remains 100 items. Evidence is
stored at
`runtime/evidence/revenue-mvp-expansion-current-pending-batch-017-live-success-20261002.json`.

A nineteenth separately approved current-state batch completed five of five
exact official API validations. Post-write aggregate review recorded 217 active
runtime redirects, 237 stored targets, and 60 untouched initial-validation
rows. The public artifact remains 100 items. Evidence is stored at
`runtime/evidence/revenue-mvp-expansion-current-pending-batch-018-live-success-20261002.json`.

A twentieth separately approved current-state batch completed five of five
exact official API validations. Post-write aggregate review recorded 222 active
runtime redirects, 242 stored targets, and 55 untouched initial-validation
rows. The public artifact remains 100 items. Evidence is stored at
`runtime/evidence/revenue-mvp-expansion-current-pending-batch-019-live-success-20261002.json`.

A twenty-first separately approved current-state batch completed five of five
exact official API validations. Post-write aggregate review recorded 227 active
runtime redirects, 247 stored targets, and 50 untouched initial-validation
rows. The public artifact remains 100 items. Evidence is stored at
`runtime/evidence/revenue-mvp-expansion-current-pending-batch-020-live-success-20261002.json`.

A twenty-second separately approved current-state batch completed five of five
exact official API validations. Post-write aggregate review recorded 232 active
runtime redirects, 252 stored targets, and 45 untouched initial-validation
rows. The public artifact remains 100 items. Evidence is stored at
`runtime/evidence/revenue-mvp-expansion-current-pending-batch-021-live-success-20261002.json`.

Before preparing or executing another LIVE batch, run
`scripts/revenue_mvp_revalidation_cadence_guard.py` against the latest private
D1 SQL export. The guard emits aggregate-only output and blocks when it observes
three or more consecutive upstream-unavailable run groups at roughly hourly
intervals. Missing or malformed evidence also fails closed. A blocked result
does not identify the scheduler owner; it forbids another LIVE batch until the
Cloudflare trigger configuration is inspected and the unexpected cadence is
resolved or explicitly accounted for. The guard does not change D1, deployment,
scheduler, publication, or credentials.

`scripts/revenue_mvp_expansion_resume_gate.py` separates that historical
failure evidence from a current dashboard observation. The historical cadence
is accounted for only when a fresh, validated Cloudflare Free observation shows
no active Cron trigger and no capacity blocker. Until that observation exists,
the gate remains blocked. Passing permits preparation of the next bounded batch
only; LIVE execution, D1 writes, and publication stay false and continue to
require a separate explicit approval.

`scripts/revenue_mvp_expansion_activation_progress.py` reclassifies the exact
300-item candidate from hash-pinned pre-expansion and post-batch snapshots. It
reports aggregate counts only and keeps remaining initial validation, retry,
active, and legacy-pending populations separate. The current snapshot records
5 completed initial validations, 173 untouched initial validations, 75 retry
rows, 49 active rows, and 3 legacy-pending rows; 124 redirect targets exist and
49 are runtime eligible. The next initial batch is capped at five, but the plan
does not permit execution or any D1 write. Sanitized evidence is stored at
`runtime/evidence/revenue-mvp-expansion-activation-progress-20261001.json`.
