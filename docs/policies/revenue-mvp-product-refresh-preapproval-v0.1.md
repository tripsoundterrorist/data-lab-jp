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

## Daily assessment boundary

`scripts/run-product-refresh-assessment-task.ps1` is the bounded, read-only
entrypoint for a daily post-Collector assessment. It reads the current public
artifact and Revenue database, persists only the rehearsal's aggregate JSON
under the ignored `logs/product-refresh-assessment` directory, and retains logs
for 30 days. It does not generate a candidate, export or query D1, call an API,
replace the public artifact, deploy, or open the Publication Gate.

The wrapper is safe to schedule after the 16:00 JST Revenue Collector, but no
schedule is created by this repository change. A
`READY_FOR_SEPARATE_REFRESH_CANDIDATE` result means that candidate preparation
may begin. `d1_refresh_required=true` means the later private D1 export and
preapproval step must cover the changed route set. `BLOCKED` must stop the
refresh path while leaving the currently published artifact unchanged.

The optional Windows schedule is configured separately and is dry-run by
default:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts/configure-product-refresh-assessment-schedule.ps1
```

After reviewing `READY_TO_CREATE`, `-Apply` creates one daily 16:30 JST task.
The installer refuses to replace or modify a same-named task whose action or
trigger differs. Scheduling only runs the read-only assessment wrapper; it does
not generate or approve a candidate and does not publish.

## Daily private candidate preparation

`scripts/run-product-refresh-candidate-task.ps1` pins the exact Revenue database
SHA-256 and invokes the existing offline candidate builder for exactly 100
cards. It writes the candidate HTML and aggregate JSON receipt only under the
user's local application-data directory, outside Git, and retains matching
artifacts for seven days. The same database hash maps to the same filenames, so
a retry cannot create multiple logical candidates.

The wrapper independently verifies the generated candidate SHA-256 and accepts
only results that keep publication, production writes, and D1 writes false. A
database race, invalid count, stale input, malformed result, missing candidate,
or hash mismatch fails closed and cannot alter the current public artifact.

The optional 16:35 JST Windows schedule is dry-run by default:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts/configure-product-refresh-candidate-schedule.ps1
```

`-Apply` creates a separate task after the 16:30 assessment. The task only
prepares a private review candidate. D1 verification, explicit user approval,
repository replacement, CI, deployment, and live verification remain separate.
