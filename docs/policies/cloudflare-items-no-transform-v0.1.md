# Cloudflare `/items/` no-transform boundary v0.1

Cloudflare Web Analytics automatic setup can inject a beacon script while HTML
passes through the edge. The exact-artifact activation therefore failed closed
and was rolled back when the edge response hash changed.

Cloudflare documents that an origin response with `Cache-Control: public,
no-transform` is not modified for automatic Web Analytics injection. The
route-specific `_headers` rule applies that directive only to `/items/*`, keeps
the rest of the site unchanged, and introduces no paid service.

This change does not reopen the scoped Publication Gate, deploy product data,
enable a CTA or affiliate eligibility, or authorize another activation. The
header must be verified on production and a static control response must prove
that the beacon is absent before a fresh artifact is reviewed and approved.
