# Affiliate CTA Canary Preflight Evidence v0.1

On 2026-09-22, after explicit user approval, the bounded one-shot preflight
checked 10 uniquely resolved items from the exact live 100-item surface.

All 10 lookups and all 10 DMM API requests completed. All 10 expected items
were returned with an affiliate URL. No rate-limit stop occurred. The safe
result contained counts and a selection digest only; no public ID, content ID,
title, source response, affiliate URL, or secret value was written to the
evidence or output.

The evidence binds the exact selection digest to the source database hash and
the currently live edge-verified artifact hash. It records zero production
writes and grants no CTA activation, D1 write, deployment, billing, or Gate
authority.

The only next action is COMPLIANCE review of this exact sanitized canary. Any
change to the selection, source database, live artifact, CTA/PR presentation,
or runtime contract invalidates this preflight and requires a fresh bounded
check.
