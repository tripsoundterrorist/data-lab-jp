# Unattended Checkpoint Storage Contract v0.1

Checkpoint Storage v0.1 stores sanitized Core checkpoints as immutable,
content-addressed objects under a temporary Phase B root. The exact envelope has
`checkpoint_storage_version`, `queue_id`, and `checkpoint`. The lowercase 64-hex
storage ID is SHA-256 of its canonical UTF-8 bytes. This is an integrity identity,
not authentication or provenance. Reads are bounded at 1 MiB and delegate field
semantics to Core `validate_checkpoint()`.

Objects are saved and read back before a Queue active reference may be adopted.
An identical existing object is idempotent; conflicts, digest errors, cross-job or
cross-queue references, missing active objects, unsafe paths, and corrupt active
objects fail closed. Existing objects are never overwritten or deleted. No delete,
clear, latest-selection, fallback, cleanup, retention, or resume API exists.

Zero or more objects may exist per job while at most one Queue reference is active.
Objects not selected by an active reference are reported as unreferenced, not
asserted to be orphans. Valid unreferenced objects are retained. Corrupt
unreferenced evidence requires manual review without automatically rewriting or
stopping unrelated Queue state. A missing directory is valid only when there is
no required active object. Phase C resolves the formal checkpoint root and reads
or inspects it without creating directories. Production checkpoint writes are
explicitly disabled, and the formal repository root cannot be used as a test
write root.
