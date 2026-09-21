# Revenue MVP rendered artifact preflight v0.1

This read-only validator binds the rendered HTML hash, candidate count, and the
reviewed `/items/` target. It rejects active or external markup, non-allowlisted
tags and attributes, a missing `noindex,nofollow` directive, an altered notice,
and count or hash mismatches.

`/items/` already maps to `items/index.html`; the preflight therefore records an
existing-route replacement review rather than creating a route. A passing
receipt is only ready for explicit activation review. Deployment and every
activation flag remain false. Rollback must restore the existing items index
and keep the scoped Gate CLOSED atomically.
