"""Read-only notification ledger diagnostics. Never repairs or sends."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import stat
import sys

import notification_ledger as ledger


RECOVERY_VERSION = "0.1"
HEALTHY = "HEALTHY"
RECOVERABLE_NO_WRITE = "RECOVERABLE_NO_WRITE"
MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
RECOVERY_BLOCKED = "RECOVERY_BLOCKED"
STALE_CANDIDATE_SECONDS = 3600
MAX_TEMP_ARTIFACTS = 64


@dataclass(frozen=True)
class RecoveryReport:
    recovery_version: str = RECOVERY_VERSION
    recovery_status: str = RECOVERY_BLOCKED
    ledger_version_detected: str | None = None
    ledger_path_class: str = "UNKNOWN"
    corruption_detected: bool | None = None
    lock_status: str = "UNKNOWN"
    temp_artifact_detected: bool | None = None
    temp_artifact_status: str = "UNKNOWN"
    record_count: int | None = None
    duplicate_identity_count: int | None = None
    action_required: str = "STOP_NOTIFICATION_SUBSYSTEM"
    checked_at_utc: str = ""
    reason_codes: tuple[str, ...] = ()

    def to_dict(self):
        result = asdict(self)
        result["reason_codes"] = list(self.reason_codes)
        return result


def _snapshot(path):
    """Use Ledger's exact record validator and duplicate-key parser, read only."""
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise OSError()
    with path.open("rb") as handle:
        data = handle.read(ledger.MAX_BYTES + 1)
    invalid = (None, None, None, True)
    if len(data) > ledger.MAX_BYTES or not data.endswith(b"\n"):
        return invalid
    try:
        rows = json.loads(data.decode("utf-8"), object_pairs_hook=ledger._unique_keys)
    except (ValueError, UnicodeError, ledger.LedgerError):
        return invalid
    if type(rows) is not list:
        return invalid
    if not rows:
        version = None  # Empty snapshots carry no record-level version evidence.
    elif any(type(row) is not dict or "ledger_version" not in row for row in rows):
        version = "UNKNOWN"
    else:
        versions = {row["ledger_version"] for row in rows}
        if versions == {"0.1"}:
            version = "0.1"
        elif versions == {"0.2"}:
            version = "0.2"
        elif versions == {"0.1", "0.2"}:
            version = "MIXED_0.1_0.2"
        else:
            version = "UNSUPPORTED"
    identities = [row.get("event_identity") for row in rows if type(row) is dict]
    safe_ids = [value for value in identities if type(value) is str and ledger.IDENTITY.fullmatch(value)]
    duplicates = len(safe_ids) - len(set(safe_ids)) if len(safe_ids) == len(rows) else None
    corrupt = any(not ledger._valid_record(row) for row in rows) or (duplicates is not None and duplicates > 0)
    return version, len(rows), duplicates, corrupt


def _lock_status(path, now):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return "ABSENT"
    if not stat.S_ISREG(info.st_mode):
        return "UNKNOWN"
    age = now.timestamp() - info.st_mtime
    return "STALE_CANDIDATE" if age >= STALE_CANDIDATE_SECONDS else "UNKNOWN"


def _temps(store):
    if not store.path.parent.exists():
        return False, "ABSENT"
    candidates = []
    # Enumerate only matching names; never open unrelated files or expose names.
    for path in store.path.parent.iterdir():
        if path.name.startswith(store.path.name + ".") and path.name.endswith(".tmp"):
            candidates.append(path)
            if len(candidates) > MAX_TEMP_ARTIFACTS:
                return True, "UNKNOWN"
    if not candidates:
        return False, "ABSENT"
    statuses = set()
    for path in candidates:
        try:
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                statuses.add("UNKNOWN")
            else:
                statuses.add("MALFORMED_CANDIDATE" if _snapshot(path)[3] else "VALID_CANDIDATE")
        except OSError:
            statuses.add("UNKNOWN")
    return True, next(iter(statuses)) if len(statuses) == 1 else "MIXED_CANDIDATES"


def inspect_ledger(store=None, *, recovery_version=RECOVERY_VERSION):
    """Return bounded metadata only. Performs no writes, lock acquisition or I/O repair."""
    now = datetime.now(timezone.utc)
    fields = {"checked_at_utc": now.isoformat().replace("+00:00", "Z")}
    try:
        if recovery_version != RECOVERY_VERSION:
            return RecoveryReport(**fields, reason_codes=("RECOVERY_VERSION_UNSUPPORTED",))
        store = ledger.NotificationLedger() if store is None else store
        if not isinstance(store, ledger.NotificationLedger):
            return RecoveryReport(**fields, reason_codes=("LEDGER_CONTRACT_INVALID",))
        try:
            store._check_path()
        except ledger.LedgerError as error:
            code = "LEDGER_TEST_PATH_REQUIRED" if error.code == "LEDGER_TEST_PATH_REQUIRED" else "LEDGER_PATH_INVALID"
            return RecoveryReport(**fields, ledger_path_class="REJECTED",
                                  recovery_status=MANUAL_REVIEW_REQUIRED,
                                  action_required="MANUAL_REVIEW", reason_codes=(code,))
        fields["ledger_path_class"] = "ISOLATED_TEST" if store.test_only else "DEFAULT_LOCAL"
        lock_path = store.path.with_name(store.path.name + ".lock")
        fields["lock_status"] = _lock_status(lock_path, now)
        fields["temp_artifact_detected"], fields["temp_artifact_status"] = _temps(store)
        try:
            version, count, duplicates, corrupt = _snapshot(store.path)
            missing = False
        except FileNotFoundError:
            # Missing is not healthy; never infer an empty delivery history for LIVE.
            version, count, duplicates, corrupt, missing = None, None, None, False, True
        fields.update(ledger_version_detected=version, record_count=count,
                      duplicate_identity_count=duplicates, corruption_detected=corrupt)
        # Recheck for a writer appearing during the diagnostic. Transaction checks again later.
        second_lock = _lock_status(lock_path, now)
        if second_lock != "ABSENT":
            fields["lock_status"] = second_lock
        reasons = []
        if corrupt:
            reasons.append("LEDGER_CORRUPT")
        if fields["lock_status"] != "ABSENT":
            reasons.append("LEDGER_BUSY")
        if fields["temp_artifact_detected"]:
            reasons.append("LEDGER_TEMP_REVIEW_REQUIRED")
        if reasons:
            return RecoveryReport(**fields, recovery_status=MANUAL_REVIEW_REQUIRED,
                                  action_required="MANUAL_REVIEW", reason_codes=tuple(sorted(reasons)))
        if missing:
            return RecoveryReport(**fields, recovery_status=RECOVERABLE_NO_WRITE,
                                  action_required="REVIEW_MISSING_LEDGER", reason_codes=("LEDGER_MISSING",))
        return RecoveryReport(**fields, recovery_status=HEALTHY, action_required="NONE",
                              reason_codes=("RECOVERY_HEALTHY",))
    except Exception:
        return RecoveryReport(**fields, reason_codes=("RECOVERY_DIAGNOSTIC_FAILED",))


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args == ["--check"]:
        report = inspect_ledger()
    elif len(args) == 3 and args[:2] == ["--check", "--test-ledger"]:
        report = inspect_ledger(ledger.NotificationLedger(Path(args[2])))
    else:
        report = RecoveryReport(reason_codes=("INSPECTION_ARGUMENTS_INVALID",))
    print(json.dumps(report.to_dict(), sort_keys=True))
    return 0 if report.recovery_status == HEALTHY else 2


if __name__ == "__main__":
    raise SystemExit(main())
