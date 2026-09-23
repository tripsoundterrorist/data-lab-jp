# Offline Wire Projection and Redaction v0.1

This policy defines a synthetic-only review boundary after the syntax and
resource gate. It does not authorize transport, live response processing, or
production activation.

| Disposition | Field scope | Evidence and treatment |
| --- | --- | --- |
| KEEP | `result`, its strict status/count/item fields, and the one item's content and affiliate-link fields | Saved official sample evidence. A new exact mapping carries only these fields to the existing strict synthetic parser. |
| DROP_SENSITIVE | `request` echo | Project control based on saved review evidence. The value is never read, compared, retained, logged, hashed, represented, or exported. Its presence returns a fixed block. |
| REJECT_UNKNOWN | Any unknown root, result, or item key | Project control. Unknown data is blocked rather than silently removed. |
| UNCONFIRMED | Additional result or item fields outside the strict subset | Their type, optionality, and meaning remain unconfirmed. This policy does not retain or interpret them. |

The contract checks field disposition evidence before projection, accepts only
exact built-in synthetic mappings, then calls the existing adapter once and the
existing owner handoff once. It does not copy or relax parser semantics, rebuild
links, or add a production projector.

The disposition evidence contains an official sample reference and digest, a
project-control reference and digest, source check date, scope, reason, and
superseded state. The unresolved live wire topic is intentionally absent from
the offline subset. Its absence does not resolve it, and every receipt keeps
connection, activation, publication, and compatibility verification false.
