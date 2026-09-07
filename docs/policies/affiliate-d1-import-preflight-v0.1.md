# Affiliate D1 Import Preflight v0.1

## Purpose

Establish fail-closed evidence that the private affiliate lookup schema and SQL candidate are safe inputs for a future manual Cloudflare D1 setup step.

This Gate is intentionally non-deploying. A `PREFLIGHT_READY` result means only that the immutable import inputs passed local validation. It never authorizes or performs a D1 write.

## Inputs

- private `affiliate-item-lookup.sql` candidate
- reviewed `runtime-candidates/affiliate-item-lookup-schema.sql`
- exact SHA-256 for the private candidate
- exact SHA-256 for the reviewed schema
- exact expected row count

Values are supplied explicitly. The preflight does not discover a Cloudflare account, D1 resource, binding, secret, or production route.

## Required checks

The preflight succeeds only when:

- candidate and schema are regular files and not symlinks
- both supplied SHA-256 values are valid and match exactly
- the existing private artifact validator returns `VALIDATED`
- candidate identity is verified
- imported row count matches exactly
- every row remains `affiliate_enabled = 0`
- rights, lifecycle, and verification fields remain pending
- `affiliate_runtime_eligible_lookup` contains zero rows

## Result semantics

A successful result returns:

- `status = PREFLIGHT_READY`
- `d1_import_allowed = false`
- `cloudflare_write_performed = false`
- `MANUAL_CLOUDFLARE_STEP_REQUIRED`

Therefore readiness evidence cannot be interpreted as production authorization.

## Non-goals

This Gate does not:

- create a D1 database
- import schema or data into Cloudflare
- configure Wrangler
- add a Pages Function binding
- create or expose secrets
- activate `/go/:public_id`
- call DMM/FANZA
- enable affiliate mappings
- alter Issue #66 decisions
- publish Public Data
- deploy or activate production

## CLI

```powershell
python scripts/affiliate_d1_import_preflight.py `
  --expected-candidate-sha256 <private-export-sha256> `
  --expected-schema-sha256 <reviewed-schema-sha256> `
  --expected-row-count <row-count>
```

The default private candidate remains Git-ignored under `runtime/private/`.

## Next boundary

After `PREFLIGHT_READY`, the next allowed step is a separately reviewed Cloudflare resource/setup action. Resource creation, import, binding, route activation, and production rollout remain distinct approval boundaries.
