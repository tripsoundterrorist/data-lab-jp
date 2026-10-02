# Doujin publication preparation v0.1

Date: 2026-10-02

Status: collection-only preparation; no publication authorization

## Scope and current evidence

The first category-publication candidate is limited to the existing isolated
sources `doujin`, `doujin_bl`, and `doujin_tl`. The aggregate audit on
2026-10-02 observed 1,350 unique items and 3,300 snapshots across these three
sources. Collection health was green, the publication boundary was closed, and
no sensitive raw key was detected.

Every observed item had a release-date-shaped value, contributor data, genre,
image data, source URL, and current price. List-price and discount observations
were present for all three sources. Series and review observations were only
partial and must remain optional.

These are collection facts, not evidence that any field may be published.

## Identity and entity boundary

- Preserve the full source tuple `(site, service, floor, content_id)`.
- Preserve `doujin`, `doujin_bl`, and `doujin_tl` as distinct internal content
  types until a reviewed product decision says otherwise.
- The observed contributor role is the official API field `maker`. Do not
  relabel it as `circle`, `brand`, `author`, or another entity type without an
  official identifier or a reviewed provenance-bearing mapping.
- Equal display names do not establish identity across sources or categories.
- Series and genre identities remain scoped to their official source type.

The aggregate-only entity integrity audit on 2026-10-02 found that every
observed `maker`, series, and genre entry in the three doujin sources carried
both an official source ID and a name, with no malformed entries and no
within-audit name variants for the same ID. Some IDs occur in more than one
content type. This supports source-scoped typed references, but does not prove
that cross-category identities may be merged. The audit intentionally emits
counts only and never entity IDs or names.

## Candidate normalized projection

The following fields may be prepared internally for later field-by-field
review. This list is not a publication allowlist:

- opaque public ID derived from the complete source namespace;
- internal content type and source identity;
- title;
- release date plus its documented source semantics;
- current price, list price, discount amount, and discount rate;
- typed `maker`, series, and genre references;
- official image facts and source product URL;
- observation timestamp and data-freshness state.

Review, campaign, sample-image, raw response, and affiliate-link fields remain
outside the candidate public projection unless separately approved.

## URL and SEO candidate

Do not change existing Revenue MVP URLs. If publication is later approved, the
candidate category namespace is `/doujin/items/{public_id}`. Before item pages
can be indexable, the category needs a reviewed canonical strategy, enough
unique user value, lifecycle handling, current data, and duplicate suppression.

The first useful surfaces should be based on verified category facts such as
new releases, observed sales, and price changes. Do not publish official rank
numbers, inferred popularity, thin filter combinations, or name-only entity
merges. No new sitemap URL is allowed during collection-only operation.

## Gates required before publication

All of the following require current evidence and explicit approval:

1. field-level storage, transformation, historical-retention, and display
   rights for the exact source;
2. image use and display requirements;
3. affiliate eligibility, deeplink method, and proximate PR disclosure;
4. preorder, discontinued, zero-result, sale, rental, and availability
   lifecycle meanings;
5. price, discount, review, campaign, and ranking semantics;
6. raw-data retention and deletion policy;
7. publication projection allowlist and secret scan;
8. category-specific canonical, robots, sitemap, and structured-data review;
9. rollback, smoke test, monitoring, and explicit Production approval.

Until every applicable Gate is complete, `publication_allowed`,
`affiliate_activation_allowed`, `sitemap_change_allowed`, and
`production_write_allowed` remain false.

## Revenue MVP boundary

This preparation must not modify the current 100-item Revenue MVP, its GA4
measurement window, affiliate runtime, D1 state, Cloudflare routes, publication
artifacts, ranking Gate, SNS policy, or the scheduled return to P0 review.
