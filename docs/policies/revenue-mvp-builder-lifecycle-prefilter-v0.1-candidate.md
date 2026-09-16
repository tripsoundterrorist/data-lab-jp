# Revenue MVP Builder Lifecycle Pre-filter v0.1 Candidate

Status: local Public Data builder integration. Publication remains closed.

The actual Public Data builder now filters `master_items` before either index or
detail objects are created. Every candidate public ID requires exactly one
sanitized `LifecycleReceipt`. The receipt contains only its version, public ID,
the existing sanitized `VerificationObservation`, a fixed inventory signal, and
a freshness boolean. It accepts no URL, API ID, affiliate ID, raw response, or
provider body.

Missing receipts, API nonvisibility, affiliate URL false or unknown, API error,
rate limit, and stale evidence exclude the item before both index and detail
generation. Duplicate, unknown-version, malformed, extra-ID, or observation-time
mismatch receipts fail the build closed. Preorder or out-of-stock alone does not
exclude an otherwise eligible item.

The receipt observation time must equal the same item's existing public
`last_observed_at`; build time cannot substitute for it. Existing Public Data
allowlists continue to prohibit rank, offset, first/source position, update
frequency, raw affiliate URLs, and credentials. Output remains
`local_validation_only`, detail CTA remains false, and production/Gate state is
unchanged.

This integration performs no new API/D1 operation, deployment, route or
scheduler change, secret mutation, production publication, or Gate mutation.
