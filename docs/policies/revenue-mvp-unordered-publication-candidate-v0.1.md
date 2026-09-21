# Revenue MVP unordered publication candidate v0.1

This is a deterministic, offline-only renderer for the exact reduced surface
approved for production-readiness review. It accepts only title, observation
time, the exact transparency notice, and an optional price with an identical
observation time. Any additional field, stale input, open activation flag, or
provenance mismatch fails closed.

The generated HTML is `noindex,nofollow`, contains no product links or
identifiers, and may only be written outside the repository. Version 0.2 keeps
only the reviewed local consent assets, production canonical, skip navigation,
bounded live regions, and required site-information links from the existing
shell; it does not load `items.js`. The receipt binds the source packet
hash, rendered artifact hash, and proposed target route. Rendering does not
publish, deploy, write D1, open a Gate, enable affiliate eligibility, or allow a
CTA. A later production build/deployment preflight and explicit user approval
for the exact hashes and target remain mandatory.

Rollback for any future separately approved activation must atomically return
the scoped Gate to CLOSED and withdraw the bound artifact and route together.
