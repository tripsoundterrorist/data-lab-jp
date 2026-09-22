# Affiliate CTA Canary Compliance Review v0.1

Decision: `APPROVE_EXACT_CANARY_ACTIVATION_REQUEST_PRESENTATION`.

This decision is limited to presenting one exact activation request for the
10-item selection bound by PR #280. It is not permission to activate a CTA,
change affiliate eligibility, write D1, deploy, change billing, expand scope,
or mutate any Production Gate.

The official response excludes API-unavailable and affiliate-ineligible items.
Accordingly, the successful one-time preflight is necessary but not sufficient
for ongoing display. Any future activation must require fresh API
revalidation before render eligibility and exact click-time revalidation. A
stale, missing, malformed, error, rate-limited, mismatched, or affiliate-URL-
absent result must both hide/disable the CTA at the applicable rendering gate
and block redirect delivery.

The fixed external-site CTA and visible compensation disclosure must remain in
the same item card, immediately adjacent. The canary may not introduce order,
rank, popularity, scarcity, urgency, purchasability, or availability claims.

Any selection/hash, presentation, revalidation, fail-closed behavior, or CI
change invalidates this review. A separate explicit user activation approval
is still required.
