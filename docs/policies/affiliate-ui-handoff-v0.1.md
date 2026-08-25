# DATA LAB Affiliate UI Handoff Contract v0.1

## Responsibility

This pure integration contract accepts only the exact safe result produced by Affiliate Link Adapter v0.1, validates UI handoff conditions, enforces PR disclosure, and returns a minimal render instruction. It never accepts an affiliate link, performs URL validation, interprets lifecycle semantics, recalculates Gate eligibility, decides availability or affiliate eligibility, or changes production UI.

## Rendering

The states are `RENDER_BLOCKED`, `RENDER_CANDIDATE`, `RENDER_ALLOWED`, and `INVALID_INPUT`. Current closed-Gate input is deterministically `RENDER_BLOCKED`, with `render_candidate=true` and `render_allowed=false`. `RENDER_ALLOWED` requires a valid known Adapter result, `ui_candidate=true`, delegated `production_render_allowed=true`, `WEB_UI`, available PR disclosure, and known reason codes. The future open-Gate case is fixture-only and does not change production status.

An affiliate CTA can never be rendered without PR/advertising disclosure; CTA-only rendering is forbidden. Wording belongs to a separate UI policy. The Handoff does not mutate Publication Gate, lifecycle, publication status, or Official Blockers and makes no availability, purchasability, or affiliate-eligibility claim.

## Input and safe output

The Adapter object must contain exactly adapter version, validation status, link status, UI candidate, production-render permission, PR requirement, and reason codes. Unexpected fields—including URLs, IDs, titles, credentials, paths, and exceptions—fail closed. Contradictory flags and unknown versions/reasons also fail closed.

Only `WEB_UI` is permitted. `PUBLIC_JSON`, `PUBLIC_DATA`, `STATIC_EXPORT`, and `API_RESPONSE_EXPORT` are blocked. Output is limited to handoff version, render status, render candidate, render allowed, PR requirement, target context, and deterministic reason codes; it never contains a link or item data.
