# Affiliate Worker Deployment Candidate v0.1

The candidate under `deployment-candidates/affiliate-worker/` packages the
reviewed affiliate runtime for a dedicated Cloudflare Worker. Workers.dev and
preview URLs are disabled. The only production route is `datalabx.jp/go/*`, and
all release facts remain hard closed so the route can only return blocked
responses during the initial smoke phase.

The committed configuration contains no API ID, affiliate ID, client-key
secret, token, or account credential. The reviewed D1 resource identity is the
same resource already bound to the Pages production environment. The rate limit
is 10 calls per 60 seconds per opaque client/item key.

The configuration deliberately omits `[limits].cpu_ms`. Cloudflare rejected
that explicit setting on the Free plan; the candidate relies on the platform's
Free-plan CPU limit instead and does not request a paid-plan override.

The compatibility date is pinned to `2026-09-11`, the latest UTC date accepted
during the 2026-09-12 JST deployment window. A future UTC date fails before
Worker creation.

This package is not a deployment authorization. Running `wrangler deploy`,
adding secrets, or attaching `datalabx.jp/go/*` requires separate approval.
