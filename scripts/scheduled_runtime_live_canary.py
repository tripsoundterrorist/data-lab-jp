"""Dedicated, explicitly confirmed Scheduler canary; never a general event CLI."""

import json
import sys

import scheduled_runtime_runner as runner


BRIDGE_VERSION = "0.1"
CONFIRMATION = "--confirm-live-canary-v0.1"
CANARY_TYPE = "JOB_WAITING_APPROVAL"


def canary_event():
    """Fresh synthetic contract; not a Queue job or an approval request."""
    return {
        "event_version": "0.1", "event_type": CANARY_TYPE,
        "job_id": "scheduler-live-canary-v0.1", "job_type": "notification_canary",
        "severity": "WARN", "state": "WAITING_APPROVAL",
        "approval_required": True, "summary_code": "SCHEDULER_LIVE_CANARY_V01",
        "occurred_at": "2026-08-27T00:00:00Z",
    }


def _result(status, code, reason, *, recovery=None, invoked=False,
            attempted=False, runtime_status=None):
    return {
        "bridge_version": BRIDGE_VERSION, "bridge_status": status,
        "canary_type": CANARY_TYPE, "runner_mode": "LIVE_NOTIFICATION",
        "recovery_status": recovery, "runtime_invoked": invoked,
        "notification_attempted": attempted, "runtime_status": runtime_status,
        "duplicate_suppressed": runtime_status == "NOTIFICATION_DUPLICATE_SUPPRESSED",
        "exit_code": code, "reason_codes": [reason],
    }


def run_canary(*, confirmed=False):
    if confirmed is not True:
        return _result("BLOCKED", 2, "EXPLICIT_CANARY_CONFIRMATION_REQUIRED")
    dispatched = False
    try:
        runner.resolve_repository_root()
        dispatched = True
        result = runner.run_once(canary_event(), mode="LIVE_NOTIFICATION",
                                 live_notification_confirmed=True)
        # Do not echo exceptions, arbitrary reason codes or untrusted status strings.
        if (not isinstance(result, runner.RunnerResult)
                or result.runner_version != "0.1" or result.mode != "LIVE_NOTIFICATION"
                or result.runner_status not in {"BLOCKED", "FAILED_SAFE", "COMPLETED"}
                or result.recovery_status not in {None, "UNKNOWN", *runner.RECOVERY_STATES}
                or result.runtime_status not in {None, *runner.RUNTIME_STATUSES}
                or type(result.runtime_invoked) is not bool
                or (result.notification_attempted is not None
                    and type(result.notification_attempted) is not bool)
                or type(result.exit_code) is not int
                or result.exit_code not in {0, 2, 3}
                or (result.exit_code == 0 and (
                    result.runner_status != "COMPLETED" or result.recovery_status != "HEALTHY"
                    or not result.runtime_invoked or result.runtime_status not in {
                        "NOTIFICATION_DELIVERED", "NOTIFICATION_DUPLICATE_SUPPRESSED"}))):
            return _result("FAILED_SAFE", 3, "RUNNER_RESULT_INVALID",
                           invoked=None, attempted=None)
        return _result(
            {0: "COMPLETED", 2: "BLOCKED", 3: "FAILED_SAFE"}[result.exit_code],
            result.exit_code, {0: "CANARY_CYCLE_COMPLETED", 2: "CANARY_CYCLE_BLOCKED",
                               3: "CANARY_CYCLE_FAILED_SAFE"}[result.exit_code],
            recovery=result.recovery_status, invoked=result.runtime_invoked,
            attempted=result.notification_attempted, runtime_status=result.runtime_status)
    except Exception:
        return _result("FAILED_SAFE", 3, "CANARY_EXECUTION_FAILED",
                       invoked=None if dispatched else False,
                       attempted=None if dispatched else False)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args != [CONFIRMATION]:
        result = _result("BLOCKED", 2, "CANARY_ARGUMENTS_BLOCKED")
    else:
        result = run_canary(confirmed=True)
    print(json.dumps(result, sort_keys=True))
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
