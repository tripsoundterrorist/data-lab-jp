# Temporal Series Filename and Identity Evidence v0.1

This memory-only Gate verifies eight properties of the v0.2 store plan:

- identical state produces an identical filename and digest;
- series, population, and timestamp changes each produce a distinct filename;
- content changes at the same identity and timestamp retain the filename but
  produce a distinct digest, providing a future conflict-detection signal;
- comparison identity differs across explicit series;
- raw series IDs are absent from planned filenames; and
- every plan remains free of filesystem access and write authorization.

The evidence returns booleans and bounded reason codes only. It exposes no
filename, digest, series ID, content ID, or serialized state. It authorizes no
filesystem or D1 operation, state write, migration, API request, active
connection, deployment, route activation, or affiliate eligibility change.
