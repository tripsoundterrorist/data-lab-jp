# Revenue MVP CONTROL CENTER Status v0.1

`scripts/revenue_mvp_control_center_status.py` composes the current live-surface,
300-item expansion, activation progress, Cloudflare resume, product-funnel,
COMPLIANCE, and ranking gates into one aggregate-only status. It does not replace
or relax any component gate and performs no network request, API request, D1
write, deployment, publication, billing change, or external write.

The current status is `REVENUE_MVP_LIVE_EXPANSION_BLOCKED`: the existing
100-item affiliate surface remains live and is the P0 revenue surface; the
300-item candidate has 300 lookup mappings, 124 redirect targets, and 49
runtime-ready routes. Next-batch preparation remains blocked until a current
Cloudflare capacity and Cron observation is recorded. The funnel window,
processed GA4 review, hash-pinned owner COMPLIANCE decision, expansion
publication, and ranking implementation review also remain incomplete.

Any disagreement between component counts or an unexpectedly permissive
component fails the aggregate status closed rather than inferring progress.
The sanitized 2026-10-01 snapshot is recorded at
`runtime/evidence/revenue-mvp-control-center-status-20261001.json`.

A read-only live smoke observation at 2026-10-01T06:27:15Z verified that the
served 100-item artifact is byte-exact with the repository artifact and retains
100 CTA disclosures, 100 image elements, noindex/nofollow, the exact canonical,
and a nine-URL sitemap that excludes item-detail and `/go/` routes. An invalid
opaque route returned 404; no valid affiliate route was requested, avoiding
measurement contamination. Evidence is at
`runtime/evidence/revenue-mvp-live-surface-smoke-20261001.json`.
