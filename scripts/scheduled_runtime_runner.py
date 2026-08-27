"""Single-cycle, safe entrypoint. No Scheduler registration or CLI LIVE activation."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

import ledger_recovery as recovery
import notification_ledger as ledger_module
import unattended_runtime as runtime


RUNNER_VERSION = "0.1"
MODES = runtime.MODES
RECOVERY_STATES = frozenset({recovery.HEALTHY, recovery.RECOVERABLE_NO_WRITE,
                             recovery.MANUAL_REVIEW_REQUIRED, recovery.RECOVERY_BLOCKED})
SUCCESS_STATUSES = frozenset({"NOTIFICATION_READY", "NOTIFICATION_DELIVERED",
                             "NOTIFICATION_SUPPRESSED", "DUPLICATE_EVENT_SUPPRESSED",
                             "NOTIFICATION_DUPLICATE_SUPPRESSED"})
RUNTIME_STATUSES = SUCCESS_STATUSES | {"INVALID_INPUT", "NOTIFICATION_FAILED_SAFE",
                                      "LIVE_NOTIFICATION_NOT_CONFIRMED", "EMERGENCY_SEND_BLOCKED"}


@dataclass(frozen=True)
class RunnerResult:
    runner_version: str
    mode: str
    runner_status: str
    recovery_status: str | None
    execution_started_at_utc: str
    execution_finished_at_utc: str
    runtime_invoked: bool
    runtime_status: str | None
    notification_attempted: bool | None
    lock_status: str
    repository_root_status: str
    exit_code: int
    reason_codes: tuple[str, ...]

    def to_dict(self):
        result = asdict(self)
        result["reason_codes"] = list(self.reason_codes)
        return result


def _utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_repository_root():
    # Resolve from installed source, never cwd or an environment variable.
    source = Path(__file__).absolute()
    if any(part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction())
           for part in (source, *source.parents)):
        raise ValueError()
    root = source.parent.parent.resolve()
    required = ("unattended_runtime.py", "unattended_job_queue.py", "ledger_recovery.py",
                "notification_ledger.py", "pushover_notification_adapter.py", "pushover_sender.py")
    if not (root / "AGENTS.md").is_file() or any(
            not (root / "scripts" / name).is_file() or (root / "scripts" / name).is_symlink()
            for name in required):
        raise ValueError()
    if ledger_module.DEFAULT_PATH.resolve().parent.parent != root:
        raise ValueError()
    return root


def runner_lock_path(root):
    identity = hashlib.sha256(os.path.normcase(str(root)).encode("utf-8")).hexdigest()
    return Path(tempfile.gettempdir()) / ("data-lab-scheduled-runner-" + identity + ".lock")


def _validate_lock_path(path):
    path = Path(path)
    if not path.is_absolute() or not path.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
        raise ValueError()
    if any(part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction())
           for part in (path, *path.parents)):
        raise ValueError()
    return path


def _safe_runtime_result(result, mode):
    if not isinstance(result, runtime.RuntimeResult):
        return False
    values = result.to_dict()
    if set(values) != runtime.OUTPUT_FIELDS or result.runtime_version != runtime.RUNTIME_VERSION or result.runtime_mode != mode:
        return False
    if type(result.runtime_status) is not str or result.runtime_status not in RUNTIME_STATUSES:
        return False
    if any(type(values[key]) is not bool for key in (
            "notification_selected", "notification_suppressed", "delivery_attempted",
            "delivery_succeeded", "approval_required", "emergency_blocked")):
        return False
    if mode == "DRY_RUN" and result.delivery_attempted:
        return False
    return True


def run_once(event=None, *, mode="DRY_RUN", live_notification_confirmed=False,
             runner_version=RUNNER_VERSION, ledger=None, credential_loader=None,
             transport=None, lock_path=None):
    """One event at most. Inject only fixture dependencies for mock testing."""
    started = _utc()
    safe_mode = mode if type(mode) is str and mode in MODES else "DRY_RUN"
    status, code, reasons = "BLOCKED", 2, ("RUNNER_INPUT_INVALID",)
    root_status, lock_status, recovery_status = "UNKNOWN", "NOT_ACQUIRED", None
    invoked, runtime_status, attempted = False, None, False
    owned, descriptor, owned_path = False, None, None
    try:
        if runner_version != RUNNER_VERSION or type(mode) is not str or mode not in MODES or type(live_notification_confirmed) is not bool:
            pass
        elif mode == "LIVE_NOTIFICATION" and not live_notification_confirmed:
            reasons = ("EXPLICIT_LIVE_CONFIRMATION_REQUIRED",)
        else:
            root = resolve_repository_root()
            root_status = "RESOLVED"
            owned_path = _validate_lock_path(runner_lock_path(root) if lock_path is None else lock_path)
            try:
                descriptor = os.open(owned_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                owned = True
                lock_status = "ACQUIRED"
            except FileExistsError:
                lock_status, reasons = "CONTENDED", ("RUNNER_ALREADY_LOCKED",)
            if owned:
                with ledger_module.ledger_for_mode(mode, ledger) as store:
                    report = recovery.inspect_ledger(store)
                    if (not isinstance(report, recovery.RecoveryReport)
                            or report.recovery_version != recovery.RECOVERY_VERSION
                            or type(report.recovery_status) is not str or report.recovery_status not in RECOVERY_STATES):
                        recovery_status, reasons = "UNKNOWN", ("RECOVERY_RESULT_INVALID",)
                    else:
                        recovery_status = report.recovery_status
                        allowed = recovery_status == recovery.HEALTHY or (
                            mode != "LIVE_NOTIFICATION" and recovery_status == recovery.RECOVERABLE_NO_WRITE)
                        if not allowed:
                            reasons = ("RECOVERY_PREFLIGHT_BLOCKED",)
                        elif event is None:
                            status, code, reasons = "IDLE", 0, ("NO_EVENT_AVAILABLE",)
                        elif mode == "MOCK_RUNTIME" and (credential_loader is None or transport is None):
                            reasons = ("MOCK_DEPENDENCIES_REQUIRED",)
                        else:
                            invoked, attempted = True, None
                            result = runtime.process_notification(
                                event, mode=mode, live_notification_confirmed=live_notification_confirmed,
                                ledger=store, credential_loader=credential_loader, transport=transport)
                            if not _safe_runtime_result(result, mode):
                                status, code, reasons = "FAILED_SAFE", 3, ("RUNTIME_RESULT_INVALID",)
                            else:
                                runtime_status, attempted = result.runtime_status, result.delivery_attempted
                                if runtime_status in SUCCESS_STATUSES:
                                    status, code, reasons = "COMPLETED", 0, ("RUNTIME_CYCLE_COMPLETED",)
                                else:
                                    status, code, reasons = "BLOCKED", 2, ("RUNTIME_CYCLE_BLOCKED",)
    except Exception:
        status, code, reasons = "FAILED_SAFE", 3, ("RUNNER_EXECUTION_FAILED",)
        if root_status == "UNKNOWN":
            root_status = "UNRESOLVED"
    finally:
        if owned:
            try:
                # Release only this invocation's inode; never remove a replacement lock.
                before = os.fstat(descriptor)
                after = owned_path.stat(follow_symlinks=False)
                same = (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
                os.close(descriptor)
                descriptor = None
                if not same:
                    raise OSError()
                owned_path.unlink()
                lock_status = "RELEASED"
            except Exception:
                lock_status, status, code, reasons = "RELEASE_FAILED", "FAILED_SAFE", 3, ("RUNNER_LOCK_RELEASE_FAILED",)
            finally:
                if descriptor is not None:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
    return RunnerResult(RUNNER_VERSION, safe_mode, status, recovery_status, started, _utc(),
                        invoked, runtime_status, attempted, lock_status, root_status, code, reasons)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    # Scheduler-facing CLI is deliberately non-live; no environment-based defaults.
    if not args:
        result = run_once()
    elif len(args) == 2 and args[0] == "--mode" and args[1] in {"DRY_RUN", "MOCK_RUNTIME"}:
        result = run_once(mode=args[1])
    else:
        now = _utc()
        result = RunnerResult(RUNNER_VERSION, "DRY_RUN", "BLOCKED", None, now, now,
                              False, None, False, "NOT_ACQUIRED", "UNKNOWN", 2,
                              ("CLI_LIVE_OR_ARGUMENTS_BLOCKED",))
    print(json.dumps(result.to_dict(), sort_keys=True))
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
