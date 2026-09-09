# Executor Result Authentication Contract v0.1

## Scope

This pure contract authenticates one fixed executor outcome against one exact
durably adopted generation. It accepts no callback, transport, path, payload,
exception, message, URL, credential, or free-form outcome text. It performs no
execution, persistence, retry, checkpoint operation, notification, production
write, publication, or Gate activation.

## Required evidence and binding

The caller supplies an exact `expected_job_id` and positive
`expected_attempt_count`, a valid `DurableExecutionAdoptionResult`, and an exact
`ExecutorResultEvidence` object. Adoption must be
`EXECUTION_ADOPTED_DURABLY / EXECUTION_ADOPTION_DURABLE`, `durable=true`, with a
positive Queue revision. Both objects must match the expected `(job_id,
attempt_count)` generation.

Executor evidence has exactly five frozen fields: `evidence_version`, `job_id`,
`attempt_count`, `outcome`, and `result_code`. Version 0.1 permits only these
internally consistent pairs:

| outcome | result_code | next_action |
| --- | --- | --- |
| `COMPLETED` | `EXECUTOR_CONFIRMED_COMPLETION` | `COMPLETE_JOB_DURABLY` |
| `FAILED_SAFE` | `EXECUTOR_CONFIRMED_SAFE_FAILURE` | `FAIL_JOB_SAFE_DURABLY` |

Unknown, missing, malformed, contradictory, secret-like, or generation-mismatched
input returns `AUTHENTICATION_REJECTED`, `authenticated=false`, `next_action=NONE`,
and one fixed reason code. Rejected output never echoes supplied identifiers or
values. Exceptions return `INTERNAL_AUTHENTICATION_ERROR` without raw details.

## Trust boundary

This is strict contract authentication and generation binding, not cryptographic
origin attestation. A directly constructed conforming object can pass. Version
0.1 has no signature, MAC, nonce, process identity, durable executor receipt, or
replay store. Callers must not interpret success as proof that an Executor ran.

The returned `next_action` is a bounded routing decision only. It does not invoke
either durable coordinator and does not authorize production writes.

## Next gate

A separate pure coordinator-input adapter may translate an authenticated result
into arguments for exactly one durable completion or failed-safe coordinator.
It must revalidate the authentication object and remain disconnected from
Executor invocation, production storage, notification, retry, and checkpoints.
