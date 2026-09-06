# DATA LAB Item Funnel Runtime Integration v0.1

## Scope

This gate executes the real `items/items.js` in a dependency-free inert Node
environment. It uses a fake DOM, bounded fixture responses, and an in-memory
analytics receiver. It performs no network request, production write, public
data deployment, or GA4 transmission.

## Verified path

- a valid local-preview index emits `view_item_list`;
- selecting its generated detail link emits `select_item`;
- a valid local-preview detail emits `view_item`;
- selecting its generated official-product link emits
  `outbound_product_click`;
- malformed index data fails closed, displays the fallback, and emits no funnel
  event.

All four events remain parameter-free. Consent enforcement remains owned by
`analytics-consent.js` and is verified separately.

## Execution boundary

CI runs the Node harness. A local machine without Node.js skips only this
runtime check; the static item UI and event-boundary tests continue to run.
