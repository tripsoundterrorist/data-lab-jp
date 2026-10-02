# Category collection value audit v0.1

`scripts/category_collection_value_audit.py` performs a read-only,
aggregate-only audit of the isolated multi-category database. It runs the
existing category health Gate first and fails closed unless integrity,
freshness, source identity, sensitive-key, and publication-boundary checks all
pass.

The output contains category-level counts only: items, snapshots, successful
runs, observation range, release-date, contributor, series, genre, price,
list-price, discount, review, and observed price-change coverage. It never
contains content IDs, product IDs, titles, URLs, raw payloads, credentials, or
affiliate identifiers.

Coverage differences are observations, not defects. A field can be absent
because the official category response does not provide it. The audit does not
infer missing values, rank categories by commercial value, authorize raw-data
retention, or establish rights to publish any field.

`READY_FOR_COLLECTION_ONLY_REVIEW` confirms only that aggregate history can be
reviewed. `publication_allowed` and `database_write_performed` remain false.
The result cannot modify the current 100-item Revenue MVP, D1, Cloudflare,
publication artifacts, sitemap, affiliate runtime, schedules, or notifications.
