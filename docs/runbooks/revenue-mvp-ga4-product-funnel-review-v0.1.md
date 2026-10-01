# Revenue MVP GA4 Product Funnel Review v0.1

Do not perform this review before 2026-10-10 JST. The measurement period is
2026-10-02 through 2026-10-08, followed by two processing days. The custom
dimensions are non-retroactive and were registered on 2026-10-01.

Use the authenticated DATA LAB GA4 property and select:

- event name: `outbound_product_click`;
- dimensions: `Item ID` and `Funnel Surface`;
- metric: event count;
- date range: 2026-10-02 through 2026-10-08, inclusive.

The site emits only opaque `itm_` public IDs and the allowlisted
`product_card` or `product_detail` surfaces for this event. Do not add titles,
destination URLs, prices, source IDs, referrers, credentials, or other GA4 data
to the review input.

Start from
`docs/examples/revenue-mvp-ga4-product-funnel-input-v0.1.json`. Keep
`ga4_processing_complete` false until the exact date range and processed report
have been confirmed. A false value with an empty row list means waiting, not
zero. Only after confirming processing may it be changed to true. A processed
report with no matching rows is then an explicit zero-click period.

Each row must contain exactly:

```json
{
  "item_id": "itm_000000000000000000000000",
  "surface": "product_card",
  "outbound_product_clicks": 0
}
```

Keep the row-level input private. Pass it locally to
`scripts/revenue_mvp_product_funnel_review_receipt.py`. Only its aggregate
receipt may be considered for `runtime/evidence/`; never commit the GA4 export
or item-level rows. The receipt does not authorize expansion, ordering,
ranking, publication, Production writes, or an SNS claim.
