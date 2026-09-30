# DATA LAB GA4 Consent Runtime Verification v0.1

## Existing implementation

DATA LAB already has a consent-first GA4 bootstrap using measurement ID
`G-ZPBQJ6137L`, a localStorage choice, advertising signals denied, manual
page-view dispatch, and four allowlisted funnel events.

## Runtime verification

A dependency-free Node harness executes the real `analytics-consent.js`
against an inert DOM. It does not load any network resource. The harness proves:

- no Google script, `gtag`, or `dataLayer` exists before a choice;
- persisted denial does not load analytics or accept events;
- a valid list or detail view that completed before first consent is recorded once
  after consent is granted, without replaying clicks or invalid page states;
- after consent, only the exact allowlisted X campaign tuple (`x`, `social`,
  and one lowercase campaign identifier) may populate GA4 campaign fields;
- arbitrary, malformed, duplicated, or non-X query parameters are not forwarded;
- explicit grant loads exactly the configured Google script;
- consent defaults are denied before the granted update;
- only allowlisted funnel events are accepted;
- product context is limited to an opaque `itm_` public ID and an allowlisted
  `product_card` or `product_detail` surface; malformed or additional fields
  fail closed, and product titles, destination URLs, prices, and source IDs are
  never forwarded;
- page view strips query, fragment, and referrer;
- revocation persists denial and reloads after prior loading.

## Production receipt verification

A bounded production check was completed on 2026-09-07 JST:

- before consent, `datalabx.jp` loaded the local consent bootstrap and no
  Google tag script;
- explicit consent loaded exactly
  `https://www.googletagmanager.com/gtag/js?id=G-ZPBQJ6137L`;
- GA4 Realtime reported one view for `DATA LAB | 作品データ分析`;
- the received event set contained `page_view`, `session_start`, and
  `first_visit`, one event each;
- no key event was recorded;
- consent was revoked after the check, the page reloaded, and the Google tag
  script was absent again.

The audit record excludes Google account details, user identifiers, and
session-bound administration URLs.

## Activation boundary

This verification does not change site HTML, consent UI, the privacy policy,
measurement ID, event names, production settings, or publication state. The
production check transmitted only the explicitly approved bounded test visit
and returned the test browser to denied consent afterward.
