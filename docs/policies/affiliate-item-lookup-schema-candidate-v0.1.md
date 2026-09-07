# DATA LAB Affiliate Item Lookup Schema Candidate v0.1

## Scope

This is an empty SQLite/D1-compatible candidate schema for the future private
`AFFILIATE_ITEM_LOOKUP` binding. It creates no Cloudflare resource, contains no
item row, and is not part of a migration or deployment configuration.

## Data boundary

The table stores only the private runtime mapping and explicit safety state:

- validated public ID;
- validated internal content ID;
- rights status;
- lifecycle status;
- verification status;
- explicit affiliate enable flag;
- update timestamp.

It has no API ID, affiliate ID, affiliate URL, DMM response, product title,
image, price, analytics, or user data column.

## Fail-closed defaults

New rows default to pending rights, pending lifecycle, pending verification,
and disabled affiliate state. A database constraint rejects any enabled row
unless rights are conditionally approved, lifecycle is resolved, and
verification passed.

The runtime-facing view returns only rows that satisfy all four explicit
conditions. Pending, failed, prohibited, disabled, malformed, or duplicate rows
remain unavailable.

## Activation boundary

The schema is stored under `runtime-candidates/` and is not imported anywhere.
Creating D1, importing mappings, configuring a binding, changing any row to
enabled, deploying a handler, or exposing a redirect requires separate review
and approval. Issue #66 and every publication and production gate remain
fail-closed.
