# Temporal Series Dry Connection Harness v0.1 Candidate

The harness invokes the isolated v0.2 runner candidate for the exact four
temporal populations in fixed order. It validates every state identity before
the first invocation and stops after the first blocked result.

Successful execution proves only that each population can reach a memory-only
write plan. Results contain aggregate statuses and counts, never series IDs,
content IDs, filenames, digests, or serialized states.

The harness is not connected to the active adapter, runner, state store, API,
scheduler, or production pipeline. It performs and authorizes no filesystem or
D1 access, state write, baseline activation, migration, deployment, route
activation, publication, or affiliate eligibility change.
