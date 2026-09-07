# DATA LAB Affiliate Item Lookup Export Preflight v0.1

## Purpose

This Gate determines whether the handed-off Revenue MVP SQLite database is a
candidate for a later private lookup export. It does not generate SQL, create or
import D1, call an API, deploy a route, enable an affiliate row, or publish data.

## Required evidence

The existing DB handoff preflight must first confirm the supplied SHA-256,
read-only audit, schema, non-empty baseline, integrity check, foreign keys, and
stable database identity. The export preflight then opens SQLite with `mode=ro`
and `PRAGMA query_only = ON` and reads only `site`, `service`, `floor`, and
`content_id`.

`PREFLIGHT_READY` requires every item to belong exactly to FANZA / digital /
videoa, every content identifier to match the runtime format, and both content
and derived public identifiers to be unique. The database digest is checked
again before and after this bounded query.

## Safe result

The machine-readable result contains aggregate counts, booleans, status, and
bounded reason codes only. It never includes a database path, SHA-256 value,
content ID, public ID, title, URL, SQL, or credential. `export_performed` and
`publication_allowed` are always false.

## Next Gate

`PREFLIGHT_READY` permits review only. Running the private exporter against the
real database requires separate approval. Inspecting or transferring the SQL,
creating or importing D1, changing eligibility, binding the runtime, deploying,
or publishing also remain separate fail-closed Gates. Issue #66 remains open.
