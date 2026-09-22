# Affiliate CTA Canary Selection v0.1

This pure contract prepares, but cannot approve or activate, an exact initial
CTA canary selection.

Every submitted item must have a unique validated opaque public ID and a fresh
sanitized DMM API observation showing exactly one expected item with an
affiliate URL. The existing official lifecycle policy must classify every item
as both a public-listing and affiliate candidate. A missing item, absent link,
API error, rate limit, malformed observation, duplicate ID, or stale/future
observation blocks the entire set and selects zero items.

The initial set is capped at 10. An internal conservative 15-minute bound is
used only for the one-time selection observation; it is not represented as an
official update-frequency rule. The redirect runtime must still revalidate the
same item through the API at click time. Affiliate URLs remain transient and
are forbidden from static/public artifacts.

The safe result contains counts only. It never returns a public ID, content ID,
title, URL, or source payload. Even a successful result keeps CTA activation,
D1 writes, and deployment false and requires a separate exact-selection and
activation approval.
