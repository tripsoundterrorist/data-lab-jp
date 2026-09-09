# Temporal Series State Store v0.2 Candidate

Status: memory-only write planning candidate.

The candidate validates an explicit v0.2 temporal series state and produces
only bounded metadata: a series-aware pseudonymous filename, document SHA-256,
and byte count. Raw series IDs, content IDs, and serialized state are not
returned.

The filename incorporates a truncated SHA-256 series token so separate series
cannot share the same population/timestamp filename. The complete serialized
document remains covered by a full SHA-256 digest and a one MiB size limit.

This candidate performs no filesystem discovery, directory creation, read,
write, rename, deletion, migration, API request, D1 operation, deployment,
baseline activation, or active-pipeline connection. A later isolated candidate
must define safe persistence and read-back behavior before any write can be
considered.
