# Offline review-candidate eligibility v0.1

The production artifact filter remains the sole path that can mark an item for
offline artifact inclusion, and it still requires a passed Publication Gate.

The separate review-only lifecycle eligibility result exists to break the
evidence-review cycle while the Gate is closed. It verifies the same sanitized
lifecycle decision, freshness, and prohibited-field boundary, but fixes
`include_in_offline_artifact`, CTA, publication, and every production authority
flag to false. It emits no API-order label or ordering, rank, ordinal, update
frequency, inventory, or sales-stop claim.

The source-artifact revalidator reports this review-only count while preserving
the actual artifact filter result. If reduced-surface semantics are unconfirmed,
the item is excluded from the artifact and the revalidation remains fail-closed.
Output is staged atomically only when explicitly requested; this change does
not write production data, mutate a Gate, invoke an API, use D1, or deploy.
