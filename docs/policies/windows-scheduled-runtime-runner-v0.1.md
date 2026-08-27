# Windows Scheduled Runtime Runner v0.1

## Purpose and architecture

Single-cycle Python entrypoint for future Scheduler invocation:
Runner -> Recovery preflight -> existing Runtime -> Ledger -> Adapter -> Sender.
Runner owns only environment/path validation, its own execution guard, delegation
and safe exit reporting. It never selects jobs, mutates Queue state, writes Ledger
records, generates messages, or calls Pushover directly.

## Default mode and entrypoint

`python -B scripts/scheduled_runtime_runner.py`

No arguments means DRY_RUN. `--mode DRY_RUN` and `--mode MOCK_RUNTIME` are also
accepted. The CLI rejects LIVE_NOTIFICATION, including confirmation flags: v0.1
does not activate LIVE via Task Scheduler. Environment variables cannot select or
promote a mode. No wrapper is needed; no ExecutionPolicy change is required.

The Python `run_once(event, ...)` API accepts an existing safe Queue event. It
delegates validation to Runtime and performs at most one call. This version does
not add an event producer, file inbox, persisted Queue or job executor. No event
means a normal IDLE completion after preflight, not a job failure.

MOCK_RUNTIME with an event requires explicit fixture credential loader and mock
transport, with a temp Ledger. The CLI has no event input and therefore only
diagnoses and exits idle. Programmatic LIVE requires the existing mode plus
`live_notification_confirmed=True`; this connection is tested only with fixtures.
No LIVE activation or smoke is performed as part of this change.

## Recovery and missing Ledger

Recovery runs before Runtime. LIVE may proceed only from HEALTHY. Missing Ledger
is RECOVERABLE_NO_WRITE, a normal safety block for LIVE; Runner never initializes
it. DRY_RUN/MOCK may diagnose this state and proceed through existing Runtime
rules. Manual review, blocked, unknown or exceptional Recovery results stop the
cycle. CRITICAL_STOP emergency blocking is never overridden.

## Single execution and concurrency

The Runner lock is distinct from Ledger locks. An exclusive-create lock named
`data-lab-scheduled-runner-<repository-hash>.lock` lives in the OS user temp
directory. It covers Recovery and the entire Runtime call. Contention immediately
exits safely without starting either. The owning invocation releases only its
own file, checking file identity before removal. Failure to release is reported.
No lock stealing, stale-age inference, kill, retries, loops or daemonization.

A crashed process may leave its lock behind. Stop all instances and obtain
explicit operator authorization for recovery; v0.1 never removes stale locks.
This guard assumes one trusted local user/temp environment and cooperating
instances. Different Windows accounts/temp roots are not a machine-wide mutex.
Use the same future Scheduler principal and do not allow overlapping tasks.
The temporary lock is the only direct Runner filesystem write.

## Paths and environment

Repository root is resolved from `__file__`, validated against required files and
the existing Ledger root. Cwd and environment variables cannot redirect it.
Unresolvable/rejected paths fail closed. Default runtime paths stay under the
existing components' definitions. Test lock overrides are temp-only API arguments,
never CLI options. Runner never changes `.env`, permissions or credentials.

## Exit codes and safe output

| Code | Meaning |
|---|---|
| 0 | Safe completion: idle, dry-run ready, mock success, suppression or duplicate |
| 2 | Safe block: invalid args/mode, missing LIVE confirmation, lock contention, recovery or Runtime block |
| 3 | Operational failure: path resolution, exception, malformed Runtime output, lock I/O/release failure |

Output is one JSON object: runner_version, mode, runner_status, recovery_status,
execution_started_at_utc, execution_finished_at_utc, runtime_invoked, runtime_status,
notification_attempted, lock_status, repository_root_status, exit_code, reason_codes.
No raw Runtime result is echoed; only allowlisted status and booleans are used.
If Runtime throws or returns malformed data, notification_attempted is null
because actual delivery may be unknown. Exceptions, paths, credentials, payload,
response, notification text and request IDs are not included. No file logging.
Developer diagnosis uses isolated tests and injected failures, not secret-bearing
tracebacks printed by the production entrypoint.

## Scheduler, AC/power and activation constraints

No Task Scheduler registration/change, Registry update, power setting, migration,
deployment, production/publication/Temporal modification or new dependency.
Collector at 16:00, Backup at 17:00 and Stale Check at 18:00 remain untouched.
The stated AC policy (no automatic sleep, display off after 10 minutes) is an
operational assumption, not enforced or modified here. Runner does not query
AC/battery status or infer it; future Scheduler AC-only conditions remain the
primary gate and require separate approval.

Future activation requires separate review: confirm Python and repository paths,
same execution user/temp root, non-overlap and AC conditions; test the DRY_RUN
entrypoint; inspect Recovery; obtain explicit approval for any Ledger initialization
or Scheduler change. LIVE activation requires another policy/CLI change and approval.
No automatic repair or persistent worker is introduced.
