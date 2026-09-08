# DATA LAB Affiliate Blocked Response Adapter Candidate v0.1

This non-deployed adapter creates empty HTTP responses only for blocked status
codes 404, 405, and 429. It applies fixed `no-store`, `no-cache`, no-referrer,
nosniff, and noindex headers without reflecting input values.

Pipeline-capable results, 302, successful statuses, malformed values, and
exceptions all become an empty 404 response. The adapter cannot set a Location
header, emit a redirect, invoke the affiliate pipeline, log, fetch, or write.

This candidate remains outside `functions/` and changes no route, binding,
deployment configuration, D1 data, eligibility, secret, or affiliate state.
The deployment preflight `response_cache_disabled` fact remains false until a
complete production response path is reviewed at a later approval boundary.
