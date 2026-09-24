# Revenue MVP official response review — 2026-09-16

This is a sanitized review of the direct DMM Affiliate Support follow-up. It
contains no raw email, sender identity, account data, affiliate ID, credential,
private URL, or screenshot. The operator-provided screenshots remain outside Git.

## Lifecycle

The response explicitly says that a zero-result item cannot be assigned one
specific cause; it may be affiliate-ineligible, sales-stopped, or non-public.
An item unavailable through the API must not be affiliated. API visibility also
does not prove ordinary stock availability because preorder and out-of-stock
items may appear. Affiliate-ineligible items must be removed from the listed
site. Affiliate URL presence represents affiliate eligibility. Periodic checks
are permitted subject to request-rate limits and bounded retry after errors.

Eight of the nine Lifecycle question IDs are resolved as operational semantics.
Removal from the public listed site is resolved, but the answer does not define
whether private audit records, database history, logs, backups, or caches may be
retained. `HISTORICAL_METADATA_RETENTION` is therefore only partially resolved.
Lifecycle remains `PARTIALLY_RESOLVED`; this document does not mutate a Gate.

## Sort semantics

`sort=rank` is described as a service-specific composite of sales and
popularity. `sort=review` is the average of ratings submitted for the content,
and product identity boundaries may differ by service. Ordering follows the API
sort order. Update timing is not public, so DATA LAB must never claim a refresh
schedule and may describe only observation timestamps. That denial resolves the
public-claim policy, but it does not define the API's actual update behavior;
the broad `UPDATE_BEHAVIOR` question is only partially resolved.

The answer does not explicitly authorize treating `offset` or response position
as a public rank, nor does it supply a safe public expression for that ordinal.
Those three question IDs remain unresolved. Four of eight Sort questions are
resolved, one is partially resolved, and three are unresolved.
`DMM_SORT_SEMANTICS` is therefore `PARTIALLY_RESOLVED`; Semantics Gate and
Publication Gate remain closed.

## Required next actions

1. Implement and test the resolved Lifecycle conditions, including public
   removal and API-unavailable handling, without enabling production publication
   or assuming that private historical retention is permitted.
2. Implement safe labels for rank/review ordering without `official ranking`,
   ordinal rank, or a claimed update interval.
3. Decide whether Revenue MVP can omit ordinal position entirely. If yes, seek a
   narrowly scoped manual review that the unresolved position fields are not
   required for the published surface; otherwise ask one bounded follow-up.
4. Re-run publication artifacts, smoke tests, rollback rehearsal, and manual Gate
   review only after the required semantics are resolved. Gate changes require a
   separate commit and explicit approval.

No publication, affiliate enablement, route activation, production write,
scheduler change, external send, or billing action is authorized here.
