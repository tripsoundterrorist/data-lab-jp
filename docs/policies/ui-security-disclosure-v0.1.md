# DATA LAB Public UI Security & Disclosure Contract v0.1

## Boundary

This pure/read-only policy adds UI security requirements after Affiliate UI Handoff. It does not validate URLs, reinterpret lifecycle or Gate state, enable an upstream-blocked render, or change production UI. Current `RENDER_BLOCKED` input produces `BLOCKED_UPSTREAM` and `render_allowed=false`.

## Disclosure and link types

`NORMAL_EXTERNAL_LINK`, `AFFILIATE_LINK`, and `INTERNAL_LINK` are distinct. Affiliate CTA requires visible, proximate, non-collapsed PR/advertising disclosure plus an external-navigation indicator. Disclosure wording is intentionally deferred to a separate UI policy. External links using a new tab require `noopener` and `noreferrer`; affiliate links additionally require `sponsored` under the initial `REL_SPONSORED_REQUIRED=true` setting. v0.1 does not infer or force `nofollow`.

## Interaction safety

Forbidden patterns include fake download/close controls, deceptive urgency or scarcity, hidden disclosure, preselected consent, confusing labels, affiliate-link disguise, destination misrepresentation, automatic redirects, click interception, and forced new tabs without user action. Affiliate CTA semantics are limited to `VIEW_PRODUCT`, `OPEN_PRODUCT_PAGE`, and `CHECK_DETAILS`; generic `DOWNLOAD`, `CONTINUE`, `NEXT`, and `OPEN` are unsafe.

The contract never claims availability, purchasability, or affiliate eligibility. Passing disclosure or dark-pattern checks does not unlock any Gate, resolve lifecycle semantics, or imply publication readiness.

## Safe result

Output is limited to policy version, UI security status, render permission, disclosure requirement, external-indicator requirement, required rel tokens, prohibited-pattern codes, and reason codes. URLs, titles, IDs, credentials, paths, and raw exceptions are neither inputs nor outputs. A fixture may reach `UI_SECURITY_PASS` only when upstream rendering is already allowed and every additional security requirement passes.

Handoff reason codes are validated against the version 0.1 allowlist; unknown codes fail closed as `INVALID_INPUT`.
