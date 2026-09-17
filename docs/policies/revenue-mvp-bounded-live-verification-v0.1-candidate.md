# Revenue MVP Bounded Live Verification v0.1 Candidate

Status: inert-by-default local adapter/harness. LIVE remains approval-bound.

The adapter accepts one private expected item identity, performs at most one
concurrent verification, checks exact content matching and affiliate-link
presence, and immediately reduces the response through `product_verification`
to a sanitized `VerificationObservation` and `LifecycleReceipt`. Private content
identity and affiliate URL values never enter the receipt, safe result, log,
exception, artifact, or repository.

Default mode is `DRY_RUN`, which performs no idempotency claim, secret access,
wait, network request, or write. `LIVE` requires a separate explicit approval,
an affirmative secret-existence check, injected transport, injected one-time
idempotency claim, clock, and bounded sleeper. It is fixed to one item and
concurrency one. Rate limiting stops immediately without retry. Only a caller-
classified transient failure may retry, at most once, with a one-to-300-second
local safety wait.

The retry maximum and five-minute ceiling follow the repository's confirmed
2026-09-16 lifecycle policy. The one-second minimum is a conservative local
guard, not a claim about an official provider request-rate limit. No new numeric
provider limit is inferred because a current public official numeric limit was
not independently available during this review.

The adapter has no HTTP client or secret loader. A separately reviewed future
runner would own the ephemeral request construction and must never expose the
request URL, credentials, API/affiliate IDs, content ID, affiliate URL, raw
response, or raw exception. A generated receipt still requires same-observation
binding before the Public Data builder may consume it.

No D1/database/production write, deployment, route, scheduler, publication,
Gate, or CTA change is included.
