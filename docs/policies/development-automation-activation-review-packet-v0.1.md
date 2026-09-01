# Development Automation Activation Review Packet v0.1

## Scope

This pure builder creates a minimal, iPhone-readable manual-review packet only
after the activation review request core returns `REVIEW_REQUEST_READY`. It
does not send a notification, collect a decision, grant approval, or activate
automation.

## Safe fields

The ready packet contains only validated repository, base branch, independently
bound full and 12-character head SHA, allowlisted request ID, fixed source,
device class and scope, and review-window duration. It contains no credentials,
tokens, environment values, paths, arbitrary labels, URLs, user free text, or
command payloads.

Rejected input produces a non-echoing blocked packet: identity and target fields
are empty, the duration is zero, and only core-owned reason codes remain.

## Safety boundary

- The existing activation preflight and review-request validator remain the
  only decision source.
- LIVE, production writes, additional cost, approval and activation are false
  in every emitted packet.
- A ready packet means only that a human may inspect it.
- No remote request, approval ingestion, Scheduler change, Git/GitHub action,
  polling, retry, write, or activation exists in this Gate.
