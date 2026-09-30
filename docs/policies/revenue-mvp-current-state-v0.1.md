# Revenue MVP Current State v0.1

`scripts/revenue_mvp_current_state.py` is the current bounded Control Center
checkpoint after the product refresh and edge verification on 2026-09-30.

It distinguishes two facts that older pre-publication checkpoints cannot
represent:

- the exact approved 100-item product-card surface at `/items/` is live;
- all 100 cards contain a proximate `【PR】` disclosure and an opaque same-origin
  `/go/itm_*` affiliate route;
- the 100 current public IDs match the D1 lookup, eligibility, redirect, and
  runtime redirect layers; and
- the global Publication Gate, paid-plan changes, unreviewed scope expansion,
  and arbitrary production writes remain closed.

The repository-held refresh evidence records the observed HTTP 200 response,
exact artifact SHA-256, 100 products, 100 official images, 100 disclosed CTAs,
three successful representative redirects, an invalid-ID 404 without a
Location header, and no private affiliate URL exposure. It also records the
first automatic 20:00 JST lifecycle revalidation: five selected, five valid,
zero disabled, and a successful task result.

Any missing, changed, malformed, or unexpectedly expanded evidence fails
closed. This checkpoint itself performs no network request, secret read, D1
access, write, deployment, redirect, billing change, or Gate mutation. Its
successful next action is `MONITOR_DAILY_REVALIDATION_AND_REVENUE_FUNNEL`.
