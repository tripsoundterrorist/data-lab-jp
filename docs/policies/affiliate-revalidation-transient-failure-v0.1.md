# Affiliate revalidation transient-failure policy v0.1

The bounded lifecycle revalidation job distinguishes confirmed product
unavailability from a transport or provider failure.

- A valid exact ItemList response refreshes the redirect target and keeps the
  item enabled.
- A successful ItemList response with no matching item is confirmed
  `NOT_AVAILABLE` and disables only that item.
- A timeout, network failure, provider error, malformed upstream response, or
  other connector failure is `UNCONFIRMED`. If any item in the bounded batch is
  unconfirmed, the entire batch stops before SQL is created and performs no D1
  write. Previously verified state remains unchanged for a later retry.

This does not automatically unlock, repair, or retry. The caller receives
`FAILED_SAFE` with `UPSTREAM_UNCONFIRMED_NO_STATE_CHANGE`; scheduled execution
must remain separately controlled. Confirmed unavailability continues to fail
closed. A future freshness-expiry policy requires a separate reviewed Gate.

The Windows schedule candidate is inert by default. After a separate explicit
approval, `configure-affiliate-revalidation-schedule.ps1 -Apply` may create one
daily 20:00 JST task. Each run processes at most five rows, ignores overlapping
starts, has a ten-minute execution limit, stores aggregate-only local logs, and
does not contain an automatic retry loop. It refuses to replace or modify an
existing mismatched task. Cloudflare Cron remains absent.
