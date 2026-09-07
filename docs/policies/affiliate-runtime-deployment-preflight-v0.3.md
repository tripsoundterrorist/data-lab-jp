# DATA LAB Affiliate Runtime Deployment Preflight v0.3

## Change from v0.2

The deployment review candidate now requires explicit evidence that the private affiliate lookup schema and disabled SQL candidate passed the dedicated D1 import preflight.

`private_lookup_import_preflight_ready` is a sanitized boolean only. No candidate path, item identifier, SQL payload, D1 identifier, account identifier, secret, or URL is accepted or exposed by this preflight.

## New blocker

When the private lookup import preflight has not been completed, the result remains `BLOCKED` with:

- `PRIVATE_LOOKUP_IMPORT_PREFLIGHT_NOT_READY`
- next action `RUN_PRIVATE_LOOKUP_D1_IMPORT_PREFLIGHT`

This blocker is propagated through the existing Revenue MVP release gate because affiliate deployment reason codes are already aggregated there.

## Required evidence

The boolean may be set true only after the separate `affiliate_d1_import_preflight.py` result is `PREFLIGHT_READY` for the exact reviewed schema SHA-256, exact private candidate SHA-256, and exact row count.

Even then:

- D1 import is not authorized
- Cloudflare write is not authorized
- required secret/data bindings must still be configured separately
- the dedicated route and rate limit remain separate requirements
- the official-answer gate remains separate
- the runtime chain and proximate PR disclosure remain separate requirements
- production deployment remains false until a later explicit approval boundary

## Current state

`current_input()` reports the inert platform adapter candidate as present but keeps `private_lookup_import_preflight_ready=false`, so deployment review remains fail-closed until real private-artifact evidence is supplied in the approved environment.
