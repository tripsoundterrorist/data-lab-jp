# Revenue MVP Product Funnel Review v0.1

This is a pure local review boundary for processed GA4 product-level
`outbound_product_click` aggregates. It performs no GA4 API call, credential
access, production write, publication change, ranking change, or external
notification.

Input is limited to a 31-day period, at most 200 unique opaque item/surface
pairs, the allowlisted `product_card` and `product_detail` surfaces, and
non-negative integer click counts. Unknown fields, malformed IDs, duplicate
pairs, invalid periods, and rows supplied before GA4 processing is declared
complete fail closed.

An incomplete processing window remains `WAITING_FOR_GA4_PROCESSING` with a
null total; it is never interpreted as zero. A completed empty window is an
explicit zero-click observation. Results are ordered deterministically for
manual review only and always require additional confirmation before any site,
SNS, product ordering, or publication decision.

The first review uses the exact 2026-10-02 through 2026-10-08 window and must
not begin before 2026-10-10 JST. The fail-closed input template is at
`docs/examples/revenue-mvp-ga4-product-funnel-input-v0.1.json`; it defaults to
processing incomplete and therefore cannot be interpreted as a zero-click
period. Operational steps are at
`docs/runbooks/revenue-mvp-ga4-product-funnel-review-v0.1.md`.
