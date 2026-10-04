# X Weekly Funnel Review v0.1

This is a pure, local review boundary for the closed Monday-through-Sunday
period. It accepts owner-supplied X metrics and consented GA4 aggregates; it
does not sign in, call an API, read credentials, post to X, change a schedule,
or write to an external service.

Every missing metric must be the exact string `NOT_ACQUIRED`. Partial observed
values are retained with acquired/missing counts, but a weekly total is emitted
only when every post has that metric. CTR and site CTA rate are calculated only
from observed integer numerator and positive denominator values. Zero or missing
denominators remain `NOT_ACQUIRED`.

The input rejects unknown fields, duplicate post identities, non-JST timestamps,
posts outside the reviewed week, unknown themes, malformed campaigns, negative
metrics, and clicks above impressions. Output is always
`ADDITIONAL_CONFIRMATION_REQUIRED`; it never declares a winning time, theme, or
link strategy from a small sample and never changes operations automatically.

`price_distribution` is an accepted measurement label for a reviewed aggregate
catalog snapshot. Accepting the label does not authorize generating or posting
that content; it only prevents an approved experiment from becoming unmeasurable.

The weekly rows connect:

`X post -> UTM campaign -> consented GA4 session -> outbound_product_click`

This is an evidence structure only. Manual interpretation must still control
for weekday, posting slot, theme, PR-link presence, and sample size under
`sns-x-operations-v0.1.md`.
