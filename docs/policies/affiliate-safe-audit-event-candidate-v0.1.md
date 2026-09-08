# DATA LAB Affiliate Safe Audit Event Candidate v0.1

This non-deployed adapter creates a bounded audit-event candidate from fixed
classifications only. Its input shape contains exactly `event`, `status`, and
one allow-listed reason code. Additional fields and unknown values fail closed.

The adapter does not accept or expose item identifiers, URLs, request data,
headers, credentials, provider payloads, or exception details. It has no logger,
storage, network access, handler, deployment configuration, or production route.

This candidate does not set `log_redaction_enabled=true` in deployment
preflight. That Gate remains closed until a later runtime integration proves
that every emitted event passes this boundary and the production logging
configuration is explicitly reviewed.
