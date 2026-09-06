# DATA LAB GA4 Consent Runtime Verification v0.1

## Existing implementation

DATA LAB already has a consent-first GA4 bootstrap using measurement ID
`G-ZPBQJ6137L`, a localStorage choice, advertising signals denied, manual
page-view dispatch, and four parameter-free funnel events.

## Runtime verification

A dependency-free Node harness executes the real `analytics-consent.js`
against an inert DOM. It does not load any network resource. The harness proves:

- no Google script, `gtag`, or `dataLayer` exists before a choice;
- persisted denial does not load analytics or accept events;
- explicit grant loads exactly the configured Google script;
- consent defaults are denied before the granted update;
- only allowlisted funnel events are accepted;
- funnel events carry no product parameters;
- page view strips query, fragment, and referrer;
- revocation persists denial and reloads after prior loading.

## Activation boundary

This verification does not change site HTML, consent UI, the privacy policy,
measurement ID, event names, production settings, or publication state. It
performs no analytics transmission and adds no dependency.
