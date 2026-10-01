# Affiliate route failure notification candidate v0.1

This pure adapter maps the aggregate affiliate revalidation wrapper result to
the existing safe notification contract. A healthy revalidation plus healthy
100-route check is suppressed. A revalidation or route-health failure produces
one fixed `JOB_FAILED_SAFE` candidate with ERROR severity, immediate delivery
class, and Pushover priority 1.

The candidate never includes a product/content identifier, route, URL,
credential, exception, response, or arbitrary message. Unknown fields,
versions, timestamps, and malformed inputs fail closed. This module performs no
filesystem, environment, network, scheduler, D1, publication, retry, repair, or
notification-send operation.

Pushover LIVE delivery remains disabled. Connecting this candidate to the
existing sender requires a separate explicit approval and must preserve the
sender's no-retry and credential-redaction controls.

The 20:00 JST wrapper invokes the sender in `DRY_RUN` only after building the
aggregate revalidation and route-health result. Healthy runs are suppressed
without reading notification credentials. Failure candidates validate only the
presence of the two required `.env` values and never attempt delivery. The
aggregate DRY_RUN result is stored with the local task log; malformed output or
any attempted delivery fails the wrapper.

After explicit owner approval, the wrapper also invokes the existing
`LIVE_NOTIFICATION` runtime only for a validated failure candidate. The
persistent notification Ledger must be healthy. Successful delivery is recorded
without message text or credentials. The incident timestamp is fixed to UTC
midnight for the current day, so repeat executions on the same UTC day are
suppressed by the Ledger; an unresolved incident may notify at most once on the
next UTC day. There is no retry, emergency priority, automatic Ledger repair, or
fallback transport. Healthy runs never invoke the sender.
