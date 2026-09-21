# Revenue MVP rendered artifact preflight v0.1

This read-only validator binds the rendered HTML hash, candidate count, and the
reviewed `/items/` target. It rejects active or unreviewed external markup,
non-allowlisted tags and attributes, a missing `noindex,nofollow` directive, an
altered notice, and count or hash mismatches. The allowlist is limited to the
existing production canonical, local consent/CSS assets, skip navigation,
bounded live regions, and required site-information links; `items.js` and all
product or affiliate links remain prohibited.

`/items/` already maps to `items/index.html`; the preflight therefore records an
existing-route replacement review rather than creating a route. A passing
receipt is only ready for explicit activation review. Deployment and every
activation flag remain false. Rollback must restore the existing items index
and keep the scoped Gate CLOSED atomically.
