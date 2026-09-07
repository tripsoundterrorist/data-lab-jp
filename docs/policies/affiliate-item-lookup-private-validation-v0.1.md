# Affiliate Item Lookup Private Validation v0.1

## Purpose

Validate the Git-ignored private `affiliate-item-lookup.sql` candidate before any D1 creation, import, binding, route activation, or publication.

## Inputs

- private SQL candidate path
- fixed schema candidate
- exact expected SHA-256 of the SQL candidate
- exact expected row count

The validator does not discover or infer these values.

## Validation boundary

The candidate passes only when all of the following hold:

- candidate and schema are regular files, not symlinks
- supplied SHA-256 is valid and exactly matches the candidate
- statement count matches the expected row count plus transaction boundaries
- only the exact exporter-owned `INSERT INTO affiliate_item_lookup (public_id, content_id, updated_at)` statement shape is present
- public IDs and content IDs are unique
- the candidate can be applied to an in-memory database using the reviewed schema candidate
- every imported row remains `affiliate_enabled = 0`
- every imported row retains the pending rights, lifecycle, and verification defaults
- `affiliate_runtime_eligible_lookup` contains zero rows

Any mismatch returns `FAIL_CLOSED` with bounded reason codes and no identifiers or URLs.

## Non-goals

This Gate does not:

- create or import a Cloudflare D1 database
- connect a Pages Function or Worker route
- use DMM/FANZA credentials or call an external API
- enable any affiliate row
- change Issue #66 decisions
- activate publication or production

## CLI

```powershell
python scripts/validate_affiliate_item_lookup_candidate.py `
  --expected-sha256 <private-export-sha256> `
  --expected-row-count <row-count>
```

The default candidate remains under the Git-ignored `runtime/private/` directory. A `VALIDATED` result is evidence only; it does not authorize D1 import or production activation.
