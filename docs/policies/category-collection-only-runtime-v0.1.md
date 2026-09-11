# Category Collection-only Runtime v0.1

This runtime collects the approved S/A expansion candidates into
`data/category-collection.db`. It never reads or writes `data/data-lab.db`, D1,
publication artifacts, the site, sitemap, or affiliate runtime state.

Configured sources are FANZA doujin (general/BL/TL), FANZA ebooks
(comic/novel/photo/BL/TL), DMM.com photo ebooks, and FANZA digital PC games.
Every source, run, item, and snapshot has a database-enforced
`publication_allowed = 0` invariant. `affiliateURL` is removed recursively from
the stored sanitized response. Credentials and credential-bearing request URLs
are never logged or stored.

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

Scheduling is a separate activation step. Do not activate it until the dry run,
isolated live canary, database audit, and operating-time review pass. Activation
does not authorize publication or affiliate use.
