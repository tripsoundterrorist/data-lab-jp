# Isolated Temporal Filesystem Persistence Candidate v0.1

This candidate is constructible only through `for_test()` with an explicit
isolated root. Tests use an OS temporary directory. It is not connected to the
active pipeline, scheduler, production state directory, publication flow, or
deployment configuration.

The candidate accepts only an exact validated v0.2 write plan and matching
bytes. It confines the fixed safe filename to the owned root, enforces the
1 MiB document limit and four-write run limit, writes an exclusive temporary
file, flushes and fsyncs it, atomically replaces the target, and verifies exact
read-back. An identical replay is a no-op; different content at the same name
is rejected. Temporary residue and uncertain outcomes require manual recovery
without retry or rollback.

All results keep `production_write_authorized=false`. No secrets, paths,
identifiers, document bytes, or raw exceptions are returned.

## Next Gate

Review test-only persistence evidence. Connecting this candidate to the
validated bundle, any non-temporary path, scheduler, or production flow needs a
separate explicit approval.
