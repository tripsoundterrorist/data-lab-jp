# DATA LAB Pushover Sender v0.1

## Scope and boundary

The sender accepts only the exact nine-field safe output of Pushover
Notification Adapter v0.1. It returns an exact nine-field safe summary and
never returns a title, message, endpoint, payload, response, request ID,
credential, exception, traceback, or path.

Credentials are read at runtime only from `.env` keys `PUSHOVER_USER_KEY` and
`PUSHOVER_APP_TOKEN`. Their values must never be logged, persisted, included in
fixtures, or exposed in results. Only the combined presence result is returned.

## Modes

- `DRY_RUN` is the default. It validates the contract and credential presence
  without constructing or sending a request.
- `MOCK_SEND` requires an injected transport and uses fixture credentials only.
- `LIVE_SEND` requires an explicit confirmation flag. Its endpoint is fixed to
  `https://api.pushover.net/1/messages.json`, method is POST, and timeout is 10
  seconds.

There is no automatic retry. Any timeout, connection error, HTTP failure,
malformed response, or internal exception becomes a bounded safe failure.
Success requires response `status == 1`; raw responses are discarded.

## Delivery policy

`IMMEDIATE` and `NORMAL` are live-send candidates. `SUPPRESSIBLE` is skipped by
default and requires explicit `send_suppressible=true`. Priority 2 is always
blocked in v0.1 even when marked as an emergency candidate. Retry, expire, and
receipt policy must be defined in a future version before emergency delivery.

The sender performs no queue mutation, scheduler or Windows configuration
change, database/state write, production/Public Data/Gate change, or deploy.
