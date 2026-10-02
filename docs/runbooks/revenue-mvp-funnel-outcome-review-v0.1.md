# Revenue MVP Funnel Outcome Review v0.1

Do not perform this review before 2026-10-10 JST. This local-only workflow
combines the exact 2026-10-02 through 2026-10-08 GA4 product-funnel input with
the exact-period DMM affiliate outcome input. It performs no sign-in, API call,
external write, Production change, publication, ranking, or catalog expansion.

Provide a private JSON object with `version`, `ga4_input`, and `dmm_input`.
`ga4_input` must follow the existing GA4 product-funnel schema, and `dmm_input`
must follow the DMM outcome schema. Never commit the completed input because
the GA4 section can contain opaque item-level rows.

Run locally:

```powershell
Get-Content -Raw <private-combined-input.json> |
  python scripts/revenue_mvp_funnel_outcome_review.py
```

The tool independently applies both existing validators. It calculates only
when both reviews are complete, their periods match exactly, the review date is
on or after 2026-10-10, and the outbound-click denominator is positive.

The calculated fields are deliberately named
`same_period_conversion_click_ratio` and
`same_period_revenue_per_click_yen`. They are same-period aggregate proxies,
not user-level attribution and not definitive CVR or EPC. DMM attribution can
include behavior that is not represented by the same-period consented GA4
click aggregate. Keep `attribution_status` as
`NOT_ESTABLISHED_BY_AGGREGATES` and require manual interpretation.

`NOT_ACQUIRED`, `NO_DATA`, incomplete processing, a pre-review date, mismatched
periods, and a zero click denominator do not produce rates. Output never
authorizes ordering, ranking, 300-item publication, Production writes, or SNS
claims.
