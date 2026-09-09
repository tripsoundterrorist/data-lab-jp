# Executor Result Coordinator Input Adapter Contract v0.1

## Scope

This pure adapter revalidates one successful Executor Result Authentication
object and maps it to fixed arguments for exactly one existing durable
coordinator. It does not import, call, wrap, or select a persistence store or
Executor. It performs no Queue read/write, notification, retry, checkpoint,
production, publication, deployment, or Gate activation operation.

## Revalidation and exact routing

The authentication module's public validator remains authoritative. The adapter
accepts only the exact frozen authentication result type with version `0.1`,
`EXECUTOR_RESULT_AUTHENTICATED`, `authenticated=true`, a safe positive execution
generation, the fixed reason code, and an outcome-consistent next action.

Exactly two routes exist:

| authenticated outcome | route | operation |
| --- | --- | --- |
| `COMPLETED` | `DURABLE_JOB_COMPLETION_COORDINATOR` | `complete_running_job_durably` |
| `FAILED_SAFE` | `DURABLE_JOB_FAILED_SAFE_COORDINATOR` | `fail_running_job_durably` |

A ready result contains only the fixed route and operation plus
`expected_job_id` and `expected_attempt_count`. These names match the existing
coordinator keyword arguments. It contains no callable, module object, store,
payload, exception, path, credential, or free-form field.

Invalid, modified, unknown, rejected, or contradictory authentication returns
`COORDINATOR_INPUT_BLOCKED`, route `NONE`, null arguments, and a fixed reason.
Exceptions fail closed without echoing input.

## Trust and invocation boundary

Readiness is only validated coordinator input. It is not proof of Executor
origin, authorization to mutate Queue state, or evidence that a coordinator was
called. The consumer must independently supply an allowed temporary store and
must retain each durable coordinator's CAS and generation checks.

## Next gate

A future dry composition contract may consume this adapter result and select an
injected coordinator callable without supplying a store or invoking it. Actual
persistence orchestration, Executor integration, and production activation stay
outside that Gate.
