# Revenue MVP DMM Outcome Review v0.1

Do not perform this review before 2026-10-10 JST. It accepts only the exact
2026-10-02 through 2026-10-08 measurement period. This workflow does not sign in, call an API, read
credentials, change Production, publish products, or write to an external
service.

Start from
`docs/examples/revenue-mvp-dmm-outcome-input-v0.1.json`. Use only values that
the owner has read from the authenticated DMM affiliate report for the exact
period. Do not include product names, product identifiers, URLs, affiliate
identifiers, credentials, or exported report rows.

`report_status` has three allowed values:

- `NOT_ACQUIRED`: the exact-period report has not been obtained;
- `NO_DATA`: the DMM UI displayed no data, which is not interpreted as zero;
- `DATA_ACQUIRED`: the exact-period conversion and revenue totals were read.

For `NOT_ACQUIRED` and `NO_DATA`, keep both metrics as the exact string
`NOT_ACQUIRED`. Only `DATA_ACQUIRED` accepts non-negative integer totals. A
numeric zero is therefore accepted only when the exact-period report was
actually obtained and explicitly showed zero. Even acquired numeric values
remain waiting through 2026-10-09.

Run locally:

```powershell
Get-Content -Raw <private-input.json> |
  python scripts/revenue_mvp_dmm_outcome_review.py
```

Keep the completed input private. The output remains manual-review evidence;
it never authorizes ranking, catalog expansion, publication, Production
writes, or an SNS claim. Compare its exact period with the processed GA4
product-funnel review before calculating CVR or revenue-per-click. If the DMM
report uses a different period or its values are not confirmed, leave the
result uncalculated.
