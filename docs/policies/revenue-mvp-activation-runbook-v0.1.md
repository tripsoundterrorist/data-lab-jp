# Revenue MVP Activation Runbook v0.1

This read-only runbook fixes the post-response activation order before any
production mutation is allowed. Current state is
`WAITING_FOR_OFFICIAL_RESPONSE`; production activation and paid-plan changes
remain false.

The required order is: sanitize and classify the DMM response; review Lifecycle
and Sort Gates; refresh and validate the public artifact; prepare an exact D1
eligibility delta; review Publication Activation; apply only the approved D1
delta; deploy public data and immutable Worker release facts; run production
smoke; verify funnel analytics and affiliate redirect; record monetization
start.

Rollback always closes Worker release facts first, then disables eligible D1
rows, removes public data, and verifies the blocked route plus public shell.
This ordering prevents a redirect from remaining open while downstream data is
being withdrawn.

The runbook consumes bounded status summaries only. It performs no API request,
D1/filesystem write, deployment, publication, route activation, affiliate
enablement, plan change, or billing change. Every production mutation requires
fresh evidence and separate explicit approval.
