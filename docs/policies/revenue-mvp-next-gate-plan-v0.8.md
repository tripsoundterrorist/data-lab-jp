# Revenue MVP Next Gate Plan v0.8

The plan now consumes a sanitized publication-artifact validation receipt.
The receipt is accepted only while its SHA-256 matches the current source DB,
the validator result is PASS, item and shard counts match, and publication,
production-write, and Gate-unlock flags remain false.

For the current 867-item DB candidate the evidence is ready, so
`PREPARE_PUBLICATION_ARTIFACT_VALIDATION` is removed from the safe local lane.
Any DB change or malformed/permissive receipt restores that action fail-closed.
This evidence does not retain the artifact and does not authorize publication.

The plan also consumes the bounded isolated active-runner candidate evidence.
When its eight checks pass, including test-only filesystem persistence, the
obsolete pipeline-preparation action is replaced by
`REVIEW_ACTIVE_RUNNER_CONNECTION_APPROVAL`. The review action does not connect
the active pipeline and grants no API, production-write, scheduler, deploy,
publication, affiliate, or billing authority. Missing, malformed, or permissive
evidence fails closed; incomplete evidence keeps the earlier connection-review
action.
