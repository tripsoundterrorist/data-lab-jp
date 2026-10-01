# Revenue MVP Cloudflare Dashboard Observation v0.1

This is a read-only manual observation. Do not change a Worker, D1 database,
route, Cron trigger, plan, billing setting, credential, secret, or deployment
while collecting the values.

Record all values from the same Cloudflare account and observation session:

1. Workers requests during the latest 24 hours.
2. Workers CPU-limit errors during the latest 24 hours.
3. D1 rows read and rows written during the latest 24 hours.
4. D1 database storage and account storage in bytes.
5. Every active Cron trigger and its schedule. The expected count is zero.

Do not infer an unavailable value, substitute zero for a missing metric, copy a
credential, or include request paths, affiliate URLs, item identifiers, API
responses, screenshots, or account identifiers in the evidence.

Provide the seven aggregate fields to
`scripts/revenue_mvp_cloudflare_observation_capture.py`. It adds the UTC
observation timestamp and emits canonical evidence only when every field is
present, the observation is current, Free capacity is not exhausted, no CPU
limit error exists, and the Cron list is empty. Otherwise it emits a blocked
result and no evidence payload.

The canonical evidence filename is
`runtime/evidence/revenue-mvp-cloudflare-dashboard-observation.json`. Creating
that file does not authorize batch preparation, LIVE execution, D1 writes,
deployment, publication, or a paid-plan change. The independent resume and
expansion gates must be rerun afterward.
