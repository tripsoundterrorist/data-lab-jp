# Category Collection-only Runtime v0.1

This runtime collects the approved S/A expansion candidates into
`data/category-collection.db`. It never reads or writes `data/data-lab.db`, D1,
publication artifacts, the site, sitemap, or affiliate runtime state.

Configured sources are FANZA doujin (general/BL/TL), FANZA ebooks
(comic/novel/photo/BL/TL), DMM.com photo ebooks, and FANZA digital PC games.
Every source, run, item, and snapshot has a database-enforced
`publication_allowed = 0` invariant. Affiliate URL and credential-like keys are
removed recursively and case/separator-insensitively from the stored sanitized
response. The health Gate independently scans persisted raw JSON for the same
key families. Credentials and credential-bearing request URLs are never logged
or stored.

The default bounded run fetches only the newest 50 items from each source using
`sort=date`, at no more than one request per source with at least 1.1 seconds
between requests. A failed source produces a generic safe error and a non-zero
overall exit code; successful source transactions remain independently recorded.

Dry run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run-category-collector-task.ps1 -DryRun
```

Live local collection:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run-category-collector-task.ps1
```

The daily collection task is active at 15:00 JST after its dry run, isolated
live canary, database audit, and operating-time review passed. It is separated
from the Revenue collector at 16:00 JST. Scheduling does not authorize
publication or affiliate use.

Read-only health check:

```powershell
python scripts/category_collection_health.py
```

The check fails closed on source-set drift, database corruption, foreign-key
violations, an incomplete or failed latest source run, data older than 26 hours, any nonzero
publication flag, or insufficient collection evidence. Its output is aggregate
and sanitized, and it never writes the database or opens publication.

The scheduled wrapper invokes this health check after every successful live
collection and appends the sanitized result to the same private log. A failed
health check makes the scheduled task return nonzero. Dry-run behavior remains
network-free and does not require an existing collection database.

The existing 18:00 JST stale-check runs the Revenue stale-run check first, then
the category health Gate. This second observation path detects a missed 15:00
category task because the last successful source observations exceed the
26-hour limit by 18:00 the following day. P1 availability checks occur only
after the P0 stale check succeeds and cannot prevent that P0 check from running.

The existing 17:00 JST daily backup task now backs up the Revenue database
first, then creates a separate validated SQLite backup of the category database.
The category backup is written atomically under the Git-ignored category backup
directory, rechecked through the same health Gate, and retained for seven daily
copies. A category backup failure returns a nonzero task result without altering
the source database. Category script availability is checked only after the
Revenue backup succeeds, so a missing or broken P1 component cannot prevent the
P0 Revenue database backup from being created.
