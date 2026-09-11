# Validated Bundle to Isolated Persistence v0.1

This test-only connector accepts one exact validated four-population state
bundle, creates the existing bounded write plans, and passes matching bytes to
an `IsolatedTemporalStateStore` constructed with `for_test()`. It is not wired
to the active pipeline, scheduler, production state directory, publication, or
deployment.

Invalid bundle, store, time, plan, serialization, or persistence output fails
closed. A downstream uncertain result requires manual recovery. Results expose
only bounded counts and reason codes; state, identifiers, paths, document bytes,
and exceptions are omitted. Production-write authorization remains false.

## Next Gate

Review this isolated integration evidence. Any active runner connection,
non-temporary root, scheduling, production write, or deployment requires a
separate explicit approval.
