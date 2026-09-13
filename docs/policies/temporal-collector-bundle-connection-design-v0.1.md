# Temporal Collector Bundle Connection Design v0.1

The current date-sorted production collector is not reused for temporal
rank/review populations because it combines live HTTP access with database
writes and has a different query population. The legacy response adapter is
also excluded because it enters the legacy runner with `dry_run=False`.

The next component must be an isolated response bridge with an injected fetcher.
It may accept only the four fixed rank/review populations, reduce responses to
the existing sanitized payload fields, and validate all four responses before
passing one atomic bundle to the approved isolated runner connection. It must
use zero retries, stop on rate limiting, and preserve the minimum one-second
request interval. Credentials remain server-side and outside every payload,
result, path, and log.

This design performs source/signature inspection only. It authorizes no
implementation, API request, state write, scheduler change, production write,
deployment, publication, affiliate activation, route, D1 operation, or billing
change. Live API execution and scheduler connection remain separate approval
Gates after the isolated bridge is implemented and reviewed.
