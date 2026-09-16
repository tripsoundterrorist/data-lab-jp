# Revenue MVP Offline Artifact Integration v0.1 Candidate

Status: in-memory connection to the actual Public Data artifact shape.
Production remains disabled.

This adapter consumes already-built `local_validation_only` Public Data files
and requires exact per-item evidence from both the merged offline lifecycle
filter and reduced-surface review. It applies the lifecycle decision to index
and detail together. Excluded or mismatched items disappear from both, and the
manifest item count plus index/detail digests are rebuilt before the existing
artifact validator runs again.

The same lifecycle observation timestamp must appear in both merged decisions.
A mismatch cannot be included. Reduced-surface review also proves API ordering
was preserved; changed ordering remains excluded rather than emitting the API
order label. Current schema emits no ordering label.

Existing artifact validation rejects `first_position`, `source_position`,
`source_offset`, `offset`, `rank`, `ranking`, and `top` before filtering. CTA
eligibility remains false in every emitted detail artifact even when the
isolated evidence says it is a candidate, because production CTA activation is
a separate Gate.

The adapter performs no filesystem/database write, D1/API request, scheduler or
route change, external send, deployment, Gate mutation, or production
publication. It does not modify the dirty builder/static-site files.
