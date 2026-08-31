"""Notification-only, best-effort persistent deduplication; no credentials."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile

from unattended_job_queue import EVENT_TYPES
import notification_ledger_record_v02 as record_codec


LEDGER_VERSION = "0.1"
DEFAULT_PATH = Path(__file__).resolve().parents[1] / "runtime" / "notification-ledger-v0.1.json"
RECORD_FIELDS = frozenset({"ledger_version", "event_identity", "event_type", "delivery_status", "recorded_at_utc"})
MAX_BYTES = 4 * 1024 * 1024
IDENTITY = re.compile(r"[0-9a-f]{64}\Z")


class LedgerError(Exception):
    """Only fixed safe codes may cross the storage boundary."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _valid_record(record):
    return record_codec.validate_record(record) in {"0.1", "0.2"}


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise LedgerError("LEDGER_CORRUPT")
        result[key] = value
    return result


class NotificationLedger:
    """Default production path, or an explicit isolated path below system temp.

    A transaction lock covers lookup, delivery and commit. No automatic lock
    stealing or retries: a stale lock requires operator recovery.
    """

    def __init__(self, path=None):
        self.path = DEFAULT_PATH if path is None else Path(path)
        self.test_only = path is not None

    def _check_path(self):
        absolute = self.path.absolute()
        if any(part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction())
               for part in (absolute, *absolute.parents)):
            raise LedgerError("LEDGER_PATH_INVALID")
        if self.test_only:
            resolved = absolute.resolve()
            if not resolved.is_relative_to(Path(tempfile.gettempdir()).resolve()) or resolved == DEFAULT_PATH.resolve():
                raise LedgerError("LEDGER_TEST_PATH_REQUIRED")
        elif absolute != DEFAULT_PATH.absolute():
            raise LedgerError("LEDGER_PATH_INVALID")

    def _read(self):
        try:
            if not self.path.exists():
                return []
            with self.path.open("rb") as handle:
                data = handle.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES or not data.endswith(b"\n"):
                raise LedgerError("LEDGER_CORRUPT")
            records = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_keys)
            if type(records) is not list or any(not _valid_record(record) for record in records):
                raise LedgerError("LEDGER_CORRUPT")
            identities = [record["event_identity"] for record in records]
            if len(set(identities)) != len(identities):
                raise LedgerError("LEDGER_CORRUPT")
            return records
        except LedgerError:
            raise
        except (ValueError, UnicodeError, TypeError):
            raise LedgerError("LEDGER_CORRUPT") from None
        except OSError:
            raise LedgerError("LEDGER_READ_FAILED") from None

    @contextmanager
    def transaction(self, *, writable=False):
        locked = False
        lock_path = self.path.with_name(self.path.name + ".lock")
        try:
            self._check_path()
            if writable:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                except FileExistsError:
                    raise LedgerError("LEDGER_BUSY") from None
                locked = True
                os.close(descriptor)
            elif lock_path.exists():
                raise LedgerError("LEDGER_BUSY")
            yield LedgerTransaction(self, self._read(), writable)
        except LedgerError:
            raise
        except OSError:
            raise LedgerError("LEDGER_IO_FAILED") from None
        finally:
            if locked:
                try:
                    lock_path.unlink()
                except OSError:
                    raise LedgerError("LEDGER_LOCK_RELEASE_FAILED") from None

    def _replace(self, records):
        temporary = None
        try:
            data = (json.dumps(records, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            if len(data) > MAX_BYTES:
                raise LedgerError("LEDGER_CAPACITY_EXCEEDED")
            with tempfile.NamedTemporaryFile(mode="wb", dir=self.path.parent,
                                             prefix=self.path.name + ".", suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            temporary = None
        except LedgerError:
            raise
        except OSError:
            raise LedgerError("LEDGER_WRITE_FAILED") from None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass


class LedgerTransaction:
    def __init__(self, ledger, records, writable):
        self._ledger, self._records, self._writable = ledger, records, writable

    def lookup(self, identity):
        return "DELIVERED" if any(row["event_identity"] == identity for row in self._records) else "NEW"

    def records_snapshot(self):
        """Return an isolated record snapshot for pure read-only decisions."""
        return [dict(record) for record in self._records]

    def record_success(self, identity, event_type):
        if not self._writable:
            raise LedgerError("LEDGER_READ_ONLY")
        record = {"ledger_version": LEDGER_VERSION, "event_identity": identity,
                  "event_type": event_type, "delivery_status": "NOTIFICATION_DELIVERED",
                  "recorded_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
        if not _valid_record(record):
            raise LedgerError("LEDGER_RECORD_INVALID")
        if self.lookup(identity) == "NEW":
            self._ledger._replace(self._records + [record])
            self._records.append(record)

    def record_success_v02(self, identity, incident_identity, event_type):
        """Append one explicit v0.2 success; never upgrade existing records."""
        if not self._writable:
            raise LedgerError("LEDGER_READ_ONLY")
        if self.lookup(identity) != "NEW":
            return "NO_CHANGE"
        record = record_codec.build_record(
            event_identity=identity,
            incident_identity=incident_identity,
            event_type=event_type,
            recorded_at_utc=datetime.now(timezone.utc).isoformat().replace(
                "+00:00", "Z"
            ),
        )
        if record is None:
            raise LedgerError("LEDGER_RECORD_INVALID")
        self._ledger._replace(self._records + [record])
        self._records.append(record)
        return "RECORDED"


@contextmanager
def ledger_for_mode(mode, supplied=None):
    if supplied is not None:
        if not isinstance(supplied, NotificationLedger):
            raise LedgerError("LEDGER_CONTRACT_INVALID")
        if mode == "MOCK_RUNTIME" and not supplied.test_only:
            raise LedgerError("LEDGER_TEST_PATH_REQUIRED")
        yield supplied
    elif mode == "MOCK_RUNTIME":
        with tempfile.TemporaryDirectory(prefix="notification-ledger-mock-") as folder:
            yield NotificationLedger(Path(folder) / "ledger.json")
    else:
        yield NotificationLedger()
