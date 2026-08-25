# DATA LAB Affiliate Link Policy v0.1

## Boundary

`affiliate_url` remains `CONDITIONALLY_APPROVED`. It is forbidden in Public JSON, Public Data, static artifacts, API response exports, and DB/public exports. This pure policy accepts only sanitized statuses and booleans; it never accepts, validates, stores, or returns a URL value. A future adapter must separately require HTTP(S), reject javascript/data/file schemes, embedded credentials, and local paths.

## UI candidate conditions

Only `WEB_UI` may become a candidate. Rights must be `CONDITIONALLY_APPROVED`, a link value must exist outside public artifacts, verification must pass, and PR/advertising disclosure must be available. PR disclosure is always required. Missing disclosure, prohibited rights, failed verification, or a public-data context returns `LINK_BLOCKED`.

Lifecycle pending may return `LINK_PENDING_LIFECYCLE_POLICY` and an internal `ui_candidate`, but never confirms availability, affiliate eligibility, or purchasability. Link absence never proves affiliate ineligibility; API visibility never proves purchasability and API invisibility never proves deletion.

## Gate separation and safe output

The policy returns only version, link status, UI candidate, production-render permission, PR requirement, lifecycle-semantics resolution, and reason codes. `LINK_AVAILABLE_FOR_UI` is not confirmed affiliate eligibility or purchasability. Production rendering remains false while Publication Gate is closed; this policy never unlocks Publication or Lifecycle Gate, resolves an Official Blocker, or changes publication status.

Allowed statuses are `LINK_AVAILABLE_FOR_UI`, `LINK_NOT_AVAILABLE`, `LINK_PENDING_LIFECYCLE_POLICY`, `LINK_BLOCKED`, and `INVALID_INPUT`. Unknown versions or statuses fail closed. URL/product/content identifiers, titles, credentials, paths, raw exceptions, and traceback data are absent from safe output.
