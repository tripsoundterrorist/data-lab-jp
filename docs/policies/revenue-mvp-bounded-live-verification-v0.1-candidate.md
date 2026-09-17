# Revenue MVP Bounded Live Verification v0.1 Candidate

Status: inert-by-default local adapter/harness. LIVE remains approval-bound.

The adapter accepts one private expected item identity and derives its public ID
from the immutable `(site, service, floor, content_id)` request context before
any claim or transport call. A public-ID mismatch, context substitution, or
incomplete binding fails closed. It performs at most one concurrent
verification, checks exact content matching and a validated affiliate-link
presence, and immediately reduces the response through `product_verification`
to a sanitized `VerificationObservation` and `LifecycleReceipt`. Private content
identity and affiliate URL values never enter the receipt, safe result, log,
exception, artifact, or repository.

Default mode is `DRY_RUN`, which performs no idempotency claim, secret access,
wait, network request, or write. `LIVE` requires a separate explicit approval,
an affirmative secret-existence check, injected transport, injected one-time
idempotency claim, atomic global-concurrency slot claim, clock, and bounded
sleeper. It is fixed to one item and concurrency one. The global slot remains a
future runner/atomic-claim blocker; a local concurrency argument alone is not
sufficient. Rate limiting stops immediately without retry. Only a caller-
classified transient failure may retry, at most once, with a one-to-300-second
local safety wait.

The retry maximum and five-minute ceiling follow the repository's confirmed
2026-09-16 lifecycle policy. The one-second minimum is a conservative local
guard, not a claim about an official provider request-rate limit. No new numeric
provider limit is inferred because a current public official numeric limit was
not independently available during this review.

Affiliate presence becomes true only for a non-empty HTTPS URL on an approved
DMM/FANZA host, without embedded credentials, whitespace, or control
characters. Backslashes and Unicode whitespace are rejected before URL parsing
so Python/WHATWG parser differences cannot upgrade presence. Absent and
invalid/unvalidated states remain distinct sanitized
states; neither exposes nor retains the URL value.

The adapter reads clocks before transport, immediately after transport, and at
evaluation. Clock reversal fails closed. Each receipt records its observation
time, freshness evaluation time, and internal maximum age. The builder
re-evaluates staleness at consumption; retry waiting cannot make an old
observation fresh. `VERIFIED` means only that a sanitized receipt was created.
It grants no lifecycle, affiliate, publication, Gate, or CTA eligibility.

The adapter has no HTTP client or secret loader. A separately reviewed future
runner would own the ephemeral request construction and must never expose the
request URL, credentials, API/affiliate IDs, content ID, affiliate URL, raw
response, or raw exception. A generated receipt still requires same-observation
binding before the Public Data builder may consume it.

The safe `database_writes=0` counter describes writes performed by this adapter
itself; injected idempotency/global claims are separately reported and are not
misrepresented as database facts. Transport attempts and API-call counters are
incremented immediately before each injected transport invocation and retained
on all clock, transport, wait, retry, and claim failure paths.

No D1/database/production write, deployment, route, scheduler, publication,
Gate, or CTA change is included.
