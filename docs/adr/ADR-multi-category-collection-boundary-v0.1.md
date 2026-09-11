# ADR: Multi-category collection boundary v0.1

Date: 2026-09-12

Status: proposed; collection-only; no publication authorization

## Decision

Revenue MVP remains P0. Multi-category work is P1/P2 and must not alter the
current production route, publication artifacts, sitemap, affiliate runtime,
D1 state, or the `FANZA/digital/videoa` collector until the Revenue MVP gates
are complete.

The first additional collection candidate is `FANZA/doujin/digital_doujin`.
Any experiment must use a separate local database and private raw-artifact root.
It is permanently fail-closed for publication unless a later, category-specific
rights, lifecycle, semantics, data-policy, artifact, deployment, and explicit
approval decision opens it.

## Evidence

The current SQLite database contains 861 items, all in
`FANZA/digital/videoa`, and 3,144 item snapshots observed between 2026-08-19
and 2026-09-11. The collector hard-codes that source tuple and `sort=date`.

An isolated, read-only FloorList call to the official DMM Affiliate API on
2026-09-12 confirmed these relevant source namespaces:

- `FANZA/doujin/digital_doujin`, `digital_doujin_bl`, `digital_doujin_tl`
- `FANZA/ebook/comic`, `novel`, `photo`, `bl`, `tl`
- `FANZA/pcgame/digital_pcgame`
- `FANZA/mono/pcgame`, `book`, `dvd`, `goods`, `anime`, `figure`
- `DMM.com/ebook/comic`, `photo`, `novel`, `otherbooks`
- `DMM.com/mono/dvd`, `cd`, `book`, `hobby`
- `DMM.com/dmmtv/dmmtv_video`

One-item, read-only ItemList capability probes confirmed successful responses
for FANZA doujin, FANZA ebook photo/comic, FANZA digital PC games, and DMM.com
ebook photo. Reported `total_count` was capped at 50,000 for the first three,
10,921 for FANZA digital PC games, and 39,744 for DMM.com photo. These are API
response observations, not verified catalog cardinalities.

Observed field shapes differ. Doujin exposed `maker`, `genre`, and price,
list-price and delivery structures. Ebook exposed `author`, `manufacture`,
`series`, `genre`, and sometimes performer/actor. PC games exposed `author`,
`maker`, `series`, and `genre`. No review object appeared in these one-item
samples, so category-wide review availability is unconfirmed.

## Current coupling and reuse

Reusable:

- source identity already includes `(site, service, floor, content_id)`;
- bounded pagination and fetch-before-write collection behavior;
- collection-run provenance and fail-closed run state;
- item observations/snapshots;
- opaque public IDs include the complete source namespace;
- publication validation and explicit gate composition.

Coupled or insufficient:

- the collector query and parser are fixed to video;
- `actress_json`, `maker_json`, `series_json`, and `genre_json` are flattened
  video-oriented columns rather than typed, provenance-bearing relations;
- no explicit internal `content_type` exists beyond API source codes;
- raw API responses are not retained, preventing future re-normalization;
- snapshots do not model list price, discount amount/rate, sale state, currency,
  delivery variant, or category-specific rank semantics;
- `source_date` is ambiguous rather than an explicit release/publication date;
- public metadata and rights maps name `actress` directly;
- affiliate D1 lookup stores only `public_id -> content_id`; the opaque ID avoids
  collision, but runtime source provenance is implicit and the export gate is
  explicitly restricted to `FANZA/digital/videoa`;
- the static route and sitemap model has no category namespace or canonical
  strategy; item pages remain noindex/local-validation-only.

## Minimal preparation before Revenue MVP completion

No production schema migration is required now. Preserve the current source
tuple and public-ID algorithm. Define the future collector boundary in design:

1. Source profile: immutable `site`, `service`, `floor`, internal
   `content_type`, adapter version, and collection/publication modes.
2. Private raw envelope: fetched timestamp, endpoint family, sanitized query
   facts, response hash, adapter version, and exact raw response. It must exclude
   credentials and full credential-bearing URLs and live outside public output.
3. Normalized core: source identity, product identity, title, canonical source
   URL, release date with semantics, image facts, typed contributors, series,
   genres, and source-specific extensions.
4. Snapshot: observed timestamp, current/list price, currency, sale/discount
   facts, review facts when present, source sort/position and rank semantics.
5. Publication projection: a separate adapter and category-specific allowlist;
   absent by default for every new category.

Raw retention needs an explicit retention/access policy before it is enabled.
Until then, a probe may validate response shape in memory and emit only bounded,
non-item capability metadata.

## Identity rules

Never treat equal display names as identity. Contributor roles (`performer`,
`author`, `circle`, `maker`, `brand`, `actor`) stay distinct. Cross-category
links require a stable official identifier scoped to its official entity type,
or an explicit reviewed mapping with provenance and confidence. Name-only links
may be search suggestions, never canonical entity merges.

## SEO boundary

Do not add new sitemap URLs during collection-only operation. After publication
approval, prefer category rankings, genuine sale/price-drop histories, new
releases, and entity pages with enough unique inventory and historical insight.
Suppress empty, near-duplicate, filter-combination, and name-only merged pages.
Canonical URLs should include a stable category namespace, for example
`/doujin/items/{public_id}`, while legacy Revenue MVP URLs remain unchanged.

## Unresolved official/compliance questions

- Whether each category and each returned field may be stored, transformed,
  retained historically, and publicly displayed.
- Image caching/hotlinking and display requirements by category.
- Affiliate-link eligibility, required disclosure placement, and deeplink rules
  for each service/floor; presence of `affiliateURL` is not authorization.
- Review/rating availability and permitted reuse.
- Lifecycle meanings for zero-result, discontinued, preorder, rental,
  subscription, and availability transitions.
- Ranking sort semantics, stability, and permission to publish derived trends.
- Raw-response retention limits and deletion obligations.
- EPC, CVR, commission rates and category-specific commercial performance;
  none are established by the API capability probe.

## Consequences

Doujin is the strongest first structural test because it is large, differs from
video in entity and price shape, and exposes list-price data in the observed
sample. It must remain isolated and collection-only. Ebook/photo follows; PC
games are lower-volume but have strong structured metadata. Physical commerce,
subscriptions, and live/online services remain research-only because stock,
shipping, entitlement, or non-item lifecycle semantics expand operational and
compliance scope.
