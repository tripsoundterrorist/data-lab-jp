# Revenue MVP Bounded Verification Runner v0.1 Candidate

Status: inert/default-deny runner and preflight. LIVE remains disabled unless a
future caller supplies every approved capability.

The runner delegates product verification exclusively to the public
`run_bounded_verification` adapter contract. It does not duplicate response,
URL, identity, lifecycle, freshness, or receipt logic and does not call private
adapter functions.

`DRY_RUN` is the default. It calls no secret checker, claim, release, transport,
sleep, storage, or write capability. LIVE preflight requires an explicit
versioned approval with the exact scope, an opaque approval identity, the same
idempotency key used by the run, a maximum 15-minute validity window, current
evaluation time, `one_shot=true`, and explicit LIVE permission. Missing,
expired, future, overlong, wrong-scope, or mismatched approval is blocked before
the secret-name checker.

The injected secret checker receives only the required names `DMM_API_ID` and
`DMM_AFFILIATE_ID`. It must return exact boolean presence facts; secret values
are neither requested nor accepted. One-time idempotency and atomic global
concurrency claims are injected boundaries with no storage implementation in
this candidate. A claimed global slot is released after every adapter path.
Claim denial, callback exception, or release failure fails closed; release
failure discards the receipt.

The runner result contains only bounded booleans, counts, status, and reason
codes. It never serializes the approval identity, idempotency key, request URL,
API/affiliate IDs, private content ID, affiliate URL, raw response, credential,
or raw exception. `adapter_database_writes=0` and `runner_writes=0` describe only
writes performed by these pure modules; injected claim implementations remain
future reviewed capabilities.

No network client, environment/secret reader, database/D1 binding, production
write, deployment, scheduler, publication, Gate, or CTA activation is included.
