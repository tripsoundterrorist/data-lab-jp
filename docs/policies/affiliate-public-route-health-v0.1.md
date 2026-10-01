# Affiliate public-route health check v0.1

`scripts/affiliate_public_route_health.py` performs a read-only aggregate check
of the live Revenue MVP affiliate surface.

It requires exactly 100 unique opaque CTA paths on `https://datalabx.jp/items/`,
sends bounded HEAD requests with at most five concurrent workers, and requires
every route to return HTTP 302 with the destination host `al.fanza.co.jp`.
Output contains counts and reason codes only; it contains no product identifier,
affiliate URL, credential, response body, or redirect path.

Any missing, duplicate, non-302, wrong-host, network, decoding, or parsing result
returns `FAILED_SAFE` with a non-zero process exit. The check performs no remote
write, repair, retry, publication, schedule change, or notification. Connecting
it to a schedule or notification path requires a separate reviewed Gate.

The reviewed Windows wrapper runs this check after its bounded 20:00 JST
revalidation cycle. Both aggregate results are written to the same local log.
Either a revalidation failure or a public-route health failure makes the Task
Scheduler run non-zero. The wrapper does not repair, retry, publish, or send a
notification; operators inspect the aggregate result separately.

The existing DATA LAB health check treats a non-zero Affiliate Revalidation
task result as `ERROR` because it may represent a broken revenue route. Other
pre-existing task result severities are unchanged.
