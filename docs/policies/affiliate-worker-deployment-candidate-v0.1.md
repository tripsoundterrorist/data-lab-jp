# Affiliate Worker Deployment Candidate v0.1

The candidate under `deployment-candidates/affiliate-worker/` packages the
reviewed affiliate runtime for a dedicated Cloudflare Worker. It is inert:
Workers.dev and preview URLs are disabled, no production route exists, and all
release facts are hard closed.

The committed configuration contains no API ID, affiliate ID, client-key
secret, token, or account credential. The reviewed D1 resource identity is the
same resource already bound to the Pages production environment. The rate limit
is 10 calls per 60 seconds per opaque client/item key.

This package is not a deployment authorization. Running `wrangler deploy`,
adding secrets, or attaching `datalabx.jp/go/*` requires separate approval.
