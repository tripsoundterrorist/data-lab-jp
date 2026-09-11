# ADR: Affiliate route Worker boundary v0.1

Date: 2026-09-12

Status: accepted for candidate preparation; not deployed

## Context

Cloudflare Pages Functions support only a documented subset of bindings. The
current Pages binding documentation does not include the Workers Rate Limiting
binding, and Pages Wrangler configuration documentation contains no
`ratelimits` configuration. The Rate Limiting API documentation defines it as a
Worker binding and requires Wrangler 4.36.0 or later.

Pages may call a separate Worker through a Service binding, but the shortest
runtime path is to route only `datalabx.jp/go/*` to a dedicated Worker while the
existing static Pages project continues to serve every other path.

## Decision

Prepare a dedicated module Worker candidate with:

- no route, workers.dev hostname, or preview URL until separate approval;
- all release facts hard-coded false;
- the existing read-only affiliate D1 binding;
- `AFFILIATE_CLIENT_RATE_LIMITER`, 10 calls per 60 seconds per opaque key;
- 10 ms CPU limit matching the Workers Free plan boundary;
- observability disabled to avoid automatic request-data logging;
- secrets absent from Git and added only through an approved encrypted channel.

The future route must be fail-closed when the Workers Free daily request limit
is exhausted. No paid-plan change is authorized. Cloudflare documents 100,000
Worker requests per day, 10 ms CPU per invocation, and 50 subrequests per
invocation for the Free plan; this handler uses one D1 query and one DMM fetch
only after all preceding guards allow it.

## Activation boundary

Before any deployment or route attachment:

1. validate with Wrangler 4.36.0 or later using a dry-run bundle;
2. establish the Worker-specific encrypted secrets, including a separately
   generated client-key secret;
3. verify the D1 and Rate Limiting bindings in an inert no-route deployment;
4. connect proximate PR disclosure and record rollback;
5. receive explicit deployment approval;
6. attach only `datalabx.jp/go/*`, initially with zero eligible D1 rows;
7. run blocked-path production smoke tests before enabling any item.

No Pages project migration is required.

## Local verification

On 2026-09-12, Wrangler 4.131.1 accepted the candidate with `deploy --dry-run`.
The bundle was 16.91 KiB uncompressed / 4.42 KiB gzip and reported exactly the
reviewed D1 binding plus `AFFILIATE_CLIENT_RATE_LIMITER` at 10 requests per 60
seconds. No upload or deployment occurred.
