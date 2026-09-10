# Temporal Filesystem Persistence / Read-back Contract v0.1 Candidate

This pure contract closes the four review gaps without accessing a filesystem.
It authorizes no connection or write.

- Trust boundary: a later implementation must receive an explicitly owned,
  confined root and must reject symlinks, traversal and non-regular targets.
- Atomicity and recovery: write a bounded temporary file, flush it, atomically
  replace, then verify an exact byte/hash read-back. Any uncertain result stops
  for manual recovery; it is never retried or rolled back automatically.
- Idempotency: an identical `(filename, SHA-256)` replay is a no-op. The same
  filename with different content is a collision and fails closed.
- Bounds: each document remains at most 1 MiB, at most four writes occur in one
  run, and the existing 45-day hot-retention boundary is retained.

No path, state document, identifier, credential or exception appears in the
result. The evaluator performs no read, write, directory creation, API request,
pipeline invocation, scheduling, publication, deployment or Gate activation.

## Next Gate

Connect this contract to the existing filesystem review evidence in memory.
That Gate must still return `connection_authorized=false` and
`write_authorized=false`. A later implementation with temporary-directory I/O
requires another explicit approval.
