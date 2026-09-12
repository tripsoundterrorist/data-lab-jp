# Revenue MVP Next Gate Plan v0.7

The plan now consumes a sanitized publication-artifact validation receipt.
The receipt is accepted only while its SHA-256 matches the current source DB,
the validator result is PASS, item and shard counts match, and publication,
production-write, and Gate-unlock flags remain false.

For the current 861-item DB candidate the evidence is ready, so
`PREPARE_PUBLICATION_ARTIFACT_VALIDATION` is removed from the safe local lane.
Any DB change or malformed/permissive receipt restores that action fail-closed.
This evidence does not retain the artifact and does not authorize publication.
