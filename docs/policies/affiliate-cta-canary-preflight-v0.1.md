# Affiliate CTA Canary Preflight v0.1

This is a bounded, one-shot, read-only orchestration contract for a future
exact CTA canary review. The default CLI has no resolver, API transport, or
execution authority and always blocks without making a request.

An authorized caller must explicitly supply 1–10 unique opaque public IDs, a
private read-only ID resolver, a sanitized DMM item fetch callback, an aware
evaluation time, the reviewed canary plan, `one_shot=true`, and a separate
execution authorization. Each item is processed sequentially. A lookup miss,
invalid response, missing product, or missing affiliate link blocks the entire
set. A rate-limit response immediately stops all remaining requests. Exceptions
fail closed without retry and without returning exception text.

The output contains counts and reason codes only. It never returns identifiers,
titles, source payloads, URLs, or credentials. Success means only
`CTA_CANARY_PREFLIGHT_READY_FOR_EXACT_REVIEW`; CTA activation, D1 writes,
deployment, production writes, and paid-plan changes remain unavailable.

Connecting real credentials, a live API transport, a D1 resolver, a scheduler,
or a production activation path requires a separate explicit Gate.
