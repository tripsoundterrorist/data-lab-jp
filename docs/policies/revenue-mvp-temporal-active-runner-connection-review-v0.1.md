# Revenue MVP Temporal Active Runner Connection Review v0.1

This Gate reviews the existing series-aware design and bounded isolated
active-runner candidate evidence. It may return
`READY_FOR_EXPLICIT_ACTIVE_CONNECTION_APPROVAL` only when the design boundary
and all eight isolated candidate checks remain exact and non-permissive.

The review executes only the candidate's existing temporary-directory evidence.
It does not connect the active runner, call an API, modify collector state,
schedule work, write production data, deploy, publish, enable affiliate routing,
or change billing. Every authority flag remains false in both ready and blocked
results.

Malformed, incomplete, changed, or permissive evidence fails closed. A ready
result advances only to `REQUEST_ACTIVE_RUNNER_CONNECTION_APPROVAL`; it is not
itself an approval and cannot be consumed as runtime authority.
