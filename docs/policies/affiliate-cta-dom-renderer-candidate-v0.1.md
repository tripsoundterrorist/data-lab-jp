# Affiliate CTA DOM Renderer Candidate v0.1

The isolated renderer creates one indivisible disclosure-and-link unit for a
future item detail page. The visible PR/affiliate compensation disclosure is
inserted immediately before the CTA within the same `aside`. The link uses only
the validated opaque public ID and a same-origin `/go/{public_id}` path; the
renderer accepts no affiliate URL or content ID.

The exact reviewed label, disclosure text, visibility flags, external indicator,
and `noopener noreferrer sponsored` tokens are mandatory. Any missing,
contradictory, unknown, or malformed value results in no DOM mutation. Text is
assigned with `textContent`, never HTML parsing.

The module remains under `runtime-candidates/` and is not imported by the live
site. It does not expose a CTA, call the route, modify production UI, deploy,
publish, enable an affiliate row, or authorize monetization.
