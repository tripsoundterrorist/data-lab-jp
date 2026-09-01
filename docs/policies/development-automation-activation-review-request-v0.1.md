# Development Automation Activation Review Request v0.1

## Scope

This pure contract validates a supplied, time-bounded Codex Remote iPhone
review request after the activation preflight is ready. It does not send a
request, observe a decision, grant approval, construct production automation,
or activate anything.

## Required request binding

- Exact repository `tripsoundterrorist/data-lab-jp` and base branch `main`.
- Exact 40-character lowercase main commit SHA, equal to the independently
  supplied expected head SHA.
- Source `CODEX_REMOTE`, device class `IPHONE`, and scope
  `DEVELOPMENT_AUTOMATION_CANDIDATE_ONLY`.
- Valid allowlisted request ID.
- Explicit supplied request and expiry times with a maximum 15-minute window.
- LIVE and production writes disabled.
- No additional cost required.

The activation preflight must independently return
`PREFLIGHT_READY_FOR_MANUAL_REVIEW`. Invalid identity, target, scope, time,
preflight, or safety evidence fails closed. Additional cost stops at
`COST_CONFIRMATION_REQUIRED`.

## Non-approval boundary

A valid record returns `REVIEW_REQUEST_READY`, but `approval_granted` and
`activation_allowed` remain false. No notification, remote request, approval
decision, production activation, LIVE behavior, Git/GitHub action, polling,
retry, or write is introduced.
