# Revenue MVP Reduced Surface Semantics Review v0.1

Status: isolated pure review candidate. Publication Gate, production, affiliate
eligibility, and external publication remain unchanged and closed.

## Allowed surface

The reduced surface is eligible only for a later Gate review when the merged
official lifecycle policy returns `ELIGIBILITY_CANDIDATE`, the displayed order
is unchanged from one API response, and the exact fixed label is either:

- `DMM API（sort=rank）取得時の並び順`
- `DMM API（sort=review）取得時の並び順`

The only timestamp label is `API取得日時`. Its value must be the timezone-aware
observation time for the same lifecycle evidence. It is not the provider's
update time, build time, or a freshness guarantee.

An affiliate CTA also requires a separately validated transient affiliate URL,
the fixed CTA presentation, and a visible, proximate PR disclosure. The raw URL
does not enter this contract or a public data artifact.

## Forbidden surface

The reduced surface excludes ordinal or rank numbers, `TOP N`, `offset`,
`first_position`, `source_position`, position-derived rank, historical rank,
update-frequency or realtime claims, latest-data claims, and availability,
purchasability, or stock claims. Items excluded by lifecycle policy do not
remain on the public surface.

`offset` and `first_position` retain only their confirmed pagination meaning.
They never authorize a public ordinal. Internal history retention is outside
this reduced surface and is not authorized here.

## Evidence required before a Gate review

This pure contract must later be connected, without weakening existing Gates,
to all of the following independently reviewed evidence:

1. lifecycle filtering before index and detail artifact creation;
2. provenance binding between the displayed API observation timestamp and the
   same lifecycle observation;
3. artifact, HTML, metadata, structured-data, and accessibility-text negative
   tests for every forbidden field and claim;
4. proof that API order was not filtered, re-sorted, or combined across pages
   when an API-order label is displayed;
5. same-item affiliate URL validation, CTA handoff, and atomic proximate PR
   disclosure;
6. fail-closed behavior for absent URLs, API nonvisibility, errors, rate limits,
   stale evidence, malformed input, and unknown versions;
7. separate Publication Gate, release, deployment, smoke, and rollback review.

The current public builder already uses an exact field allowlist, forbids raw
affiliate URLs and source offsets/positions, fixes CTA eligibility to false,
and emits `local_validation_only`. Those controls are useful evidence but do
not connect this contract or open a Gate. The current release Gate also reports
the affiliate runtime as not connected.

## Official follow-up boundary

No additional official inquiry is required for this reduced surface while it
omits every ordinal/position and update-frequency claim, displays only the API
observation timestamp, removes lifecycle-excluded products, and does not rely
on internal historical retention. Any later ordinal, rank-history, update
cadence, public archive, or service-crossing comparison requires a separate
official-confirmation review.

`REVIEW_CANDIDATE` means only that this bounded contract may enter a separate
manual Gate review. The module always returns false for Publication Gate
mutation, production publication, and external sending.
