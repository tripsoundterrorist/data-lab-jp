# Temporal Dry Connection Contract Review v0.2

The public validated state bundle contract is now available. Static review
confirms the adapter can receive its validated state tuple without private
validator reuse or duplicate payload validation.

The next isolated Gate is `CONNECT_ISOLATED_BUNDLE_TO_DRY_HARNESS`. This means a
memory-only candidate connection only. The active adapter, runner, state store,
API, scheduler, and production pipeline remain outside the boundary, and all
write, activation, migration, deployment, and eligibility permissions remain
false.
