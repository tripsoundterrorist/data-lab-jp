# Revenue MVP Product Refresh Preapproval v0.1

This Gate joins the existing bounded product-refresh checks into one offline,
fail-closed preapproval step. It does not call the provider API, query or write
D1, replace `items/index.html`, deploy, change the Publication Gate, or approve
production.

The latest successful Collector run is treated as the official-response input.
The Gate requires exactly 100 fresh, uniquely identified items with observed
affiliate links, official image hosts, prices, and lifecycle evidence. It then
builds the existing deterministic review candidate outside the repository.

A separately captured, hash-pinned private D1 SQL export is loaded into isolated
in-memory SQLite. Only inserts into the three affiliate runtime tables are
accepted. The candidate must have exact 100/100 lookup, eligibility, redirect,
and runtime-redirect coverage. Every route newly introduced relative to the
current HTML must also have a latest `VALID`, enabled revalidation event no more
than 48 hours old.

Both the private D1 export and candidate output must remain outside the
repository. If any identity, count, freshness, runtime coverage, or SQL boundary
fails, the candidate is deleted and the Gate returns `BLOCKED`.

Example after a separate read-only D1 export has been captured:

```powershell
python scripts/revenue_mvp_product_refresh_preapproval.py `
  --source items/index.html `
  --db data/data-lab.db `
  --d1-export C:\private\affiliate-runtime-export.sql `
  --output C:\private\items-index-candidate.html `
  --expected-db-sha256 <exact-db-sha256> `
  --expected-d1-sha256 <exact-export-sha256> `
  --evaluated-at <utc-timestamp>
```

`PRODUCT_REFRESH_READY_FOR_EXPLICIT_APPROVAL` means only that an exact candidate
may be presented to the user. Production replacement remains a separate,
explicitly approved action followed by CI, edge verification, and evidence
recording.
