# Doujin compliance response intake v0.1

This intake is for a future reviewed official response to the fixed question
IDs emitted by `doujin_compliance_handoff.py`. It does not send a request and
must not store the raw email, support message, URL, sender identity, account
details, credentials, or product data.

Record only the official evidence type and authority, a non-sensitive internal
reference, the received timestamp, and one explicit state per fixed question:

- `RESOLVED_ALLOW`
- `RESOLVED_DENY`
- `RESOLVED_REQUIREMENTS`
- `UNRESOLVED`
- `CONTRADICTORY`

A resolved state is accepted only when that question ID is also present in the
explicitly-answered set. Missing questions, inferred answers, unsafe evidence,
unknown states, or an altered question set fail closed. Partial and
contradictory responses remain pending.

Even a complete official response becomes only
`READY_FOR_SEPARATE_COMPLIANCE_DECISION`. It does not approve COMPLIANCE,
change a Gate, allow publication, activate affiliate links, or authorize any
Production operation. 03 COMPLIANCE must review the actual official evidence
and record a separate scoped decision.
