# Affiliate Route Rollback Plan v0.1

## Trigger

Rollback is mandatory for an unexpected redirect, disclosure/CTA separation,
missing rate limiting, identifier or URL leakage, incorrect eligibility,
upstream response ambiguity, elevated error rate, unexpected cost/plan state,
or any failed production smoke check.

## Pre-deployment evidence

Before route attachment, record only sanitized facts: reviewed Worker version,
route absence, Pages smoke status, D1 schema/counts with zero enabled rows,
binding names, Free-plan status, and rollback operator availability. Never
record secret values, account identifiers, database identifiers, item IDs,
affiliate URLs, request URLs, or client addresses.

## Ordered rollback

1. Detach exactly the affiliate Worker route. Do not change the Pages custom
   domain or other routes.
2. Confirm the existing Pages home and information pages still serve normally.
3. Confirm `/go/{opaque-id}` no longer redirects and fails closed.
4. Preserve the Worker version for forensic comparison; do not redeploy it.
5. Preserve D1 schema/data and make no new eligibility changes. Route detachment
   is the primary kill switch and does not depend on a D1 write succeeding.
6. Record a sanitized incident summary with classifications only.

If exact route detachment cannot be verified, stop. Do not attempt broad route,
zone, domain, Pages project, D1, or secret deletion as an improvised rollback.

## Verification

- Affiliate route is absent.
- Affiliate paths produce no redirect.
- Home, disclosure, privacy, terms, contact, robots and sitemap remain available.
- D1 schema is unchanged and secret values were not read or exposed.
- No paid-plan or billing change occurred.

## Reactivation

Reactivation requires a known root cause, reviewed fix, green local and GitHub
tests, inert deployment preflight, blocked-path production smoke, and a new
explicit approval. A previous deployment approval cannot be reused.

This document and `scripts/affiliate_route_rollback_plan.py` are instructions
only. They execute no command and authorize no production mutation.
