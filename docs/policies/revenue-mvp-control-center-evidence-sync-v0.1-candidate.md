# Revenue MVP Control Center Evidence Sync v0.2 Candidate

This read-only contract separates evidence collection from pure evaluation. It
does not replace or relax the existing Control Center checkpoint.

## Reviewed baseline

The evaluator accepts only
`revenue-mvp-control-center-reviewed-baseline-v0.1.json`. That manifest binds
the reduced-surface review to a fixed `main` commit, expected contract
versions, an allowlist of tracked paths, and canonical LF-normalized SHA-256
digests. A semantic manifest digest is fixed independently in the evaluator.
The baseline is not generated from the currently imported dependency constants.

Builder lifecycle prefiltering and saved lifecycle receipts each have their own
implementation-and-test path bindings. Neither is represented by a fixed
boolean assertion.

## Collector and evaluator

The collector reads only the allowlisted tracked paths and gathers their
canonical hashes plus current contract versions. It does not infer operational
facts. The pure evaluator compares that collected state with the reviewed
baseline.

Unknown versions, missing paths, unreadable files, hash mismatch, malformed or
tampered manifests, and independent builder or saved-receipt binding mismatch
all fail closed. `official_response_pending` becomes false only after every
required reduced-surface baseline comparison succeeds. Full and expanded
surfaces remain pending.

The current tracked checkout still lacks current source DB/public artifact
binding, fresh read-only production D1 reconfirmation, and manual reduced-
surface Gate review. The normal result is therefore
`CONTROL_CENTER_EVIDENCE_SYNCED_BLOCKED` with exactly those three operational
blockers. If all three are independently confirmed, the strongest result is
only `CONTROL_CENTER_REDUCED_SURFACE_REVIEW_CANDIDATE`.

Publication, production activation, affiliate eligibility, and Gate mutation
remain false for every outcome. The blocked CLI result exits nonzero so
automation cannot treat synchronization as readiness.

The module performs no API call, network access, secret read, source DB read,
filesystem write, D1 operation, deployment, scheduler action, publication,
route activation, affiliate enablement, or Gate mutation. It does not consume
untracked official-response files.
