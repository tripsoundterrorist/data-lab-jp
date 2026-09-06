# DATA LAB Affiliate Runtime DMM Connector v0.1

## Scope

The connector supplies the two trusted callbacks required by
`affiliate_runtime_resolution.py`: read-only public-ID resolution and a
single-item DMM ItemList request. It has no CLI, redirect, HTML renderer,
publication action, or deployment action.

## Database boundary

The public ID is resolved from `items(site, service, floor, content_id)` with
SQLite URI `mode=ro` and `PRAGMA query_only = ON`. The database is never
created, migrated, or modified. Internal content IDs are returned only to the
in-process resolver callback.

## API boundary

The API callback requires an already resolved content ID and configured
`DMM_API_ID` / `DMM_AFFILIATE_ID`. It sends one ItemList request with
`cid`, `hits=1`, and `offset=1`. The response is returned in memory only
to the guarded resolver; this module never logs or persists it.

Credentials, request URLs, affiliate URLs, hostnames, titles, content/product
IDs, response bodies, and upstream exception details are not emitted by the
connector.

## Activation boundary

This module is inert until a trusted runtime explicitly supplies its callbacks
to the existing resolver. It does not change Issue #66, lifecycle, rights,
verification, publication, affiliate integration, or production deployment
gates. CI uses only a temporary SQLite database and dummy API response.
