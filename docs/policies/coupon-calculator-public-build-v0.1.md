# Coupon calculator public build preparation v0.1

## Authority and state

The owner approved six-file local implementation and tests on 2026-11-19 JST.
This is not commit/push/PR/merge, publication or Production configuration approval.
PR 457 stored the existing default-off calculator candidate on main; it did not
enable it. Do not infer release authority from a passing build or this document.

## Build contract

- `--with-coupon-calculator` explicitly adds the calculator to an already-public
  coupon article; `--without-coupon-calculator` and the default omit it.
- The review transform is not used to create public output. A review/noindex
  article, missing/wrong canonical, drifted template or repeated integration is
  refused. No noindex directive is silently removed.
- With existing Production flags `--with-books-device --with-article-navigation`,
  the default remains 27 files. Opt-in output has 29: only coupon-help.html changes,
  plus same-origin coupon-calculator/candidate.css and candidate.js.
- Existing headers, CSP, sitemap, robots, consent/navigation assets and product
  listings are unchanged. The calculator code neither persists nor transmits input
  values and adds no explicit analytics emission. On 2026-11-20 JST the existing
  DATA LAB Web stream's enhanced form measurement was read as ON; no setting was
  changed. Public output therefore uses a labelled input group and two ordinary
  buttons, with no form element, native submit/reset or synthesized form event.
  The release-only adapter preserves the arithmetic and implements explicit local
  reset. Original review assets remain unchanged. This removes native form-event
  triggers; it is not proof of every behavior of the remote analytics tag.
- The calculation applies only to the documented purchase-point formula. BOOKS,
  unrelated campaigns and unknown applicability remain excluded. It does not
  determine coupon eligibility, availability, prices, or purchase recommendations.

## Offline validation and release limits

Tests use pure in-memory bundles, inert DOM and disposable isolated build copies.
They cover default identity, explicit opt-in, exact output set, rollback, dry-run,
failed-source preservation and no new security-header/transport permission.
Do not serve live-capable analytics output merely to inspect it. Browser/CSP,
mobile and accessibility validation remain distinct from offline test success.

Google documents automatic form_start/form_submit events and their form metadata:
https://support.google.com/analytics/answer/9216061?hl=en . The observed ON setting
does not prove calculator input values are collected or that events have occurred;
the calculator is not public. A separately approved browser receipt check can
verify the eventual release environment; no extra telemetry is added for it.

An actual public release needs separate approval of the exact implementation,
reader copy, deployment scope and existing Cloudflare build-command change.
Do not update that command, enable a flag, send analytics or click advertisements
from this implementation task.

## Rollback preparation

Removing the opt-in flag or explicitly supplying `--without-coupon-calculator`
rebuilds the exact baseline. The atomic builder replaces the output tree rather
than retaining stale calculator assets. Stale/extra files fail validation.
No configuration change, deployment or revert is automatically authorized here.
