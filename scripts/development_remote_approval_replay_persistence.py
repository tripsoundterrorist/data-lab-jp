"""Test-scoped durable persistence for consumed remote approvals."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Iterator

import development_remote_approval_replay_record as record_core


PERSISTENCE_VERSION = "0.1"
RESULT_VERSION = "0.1"
MAX_BYTES = 256 * 1024
ENVELOPE_FIELDS = frozenset({"persistence_version", "revision", "records"})
FORMAL_REPO_ROOT = Path(__file__).resolve().parents[1]
_TEST_TOKEN = object()
_READ_ONLY_TOKEN = object()
_REPARSE_POINT = 0x400


@dataclass(frozen=True)
class ReplayLoadResult:
    result_version: str
    status: str
    revision: int | None
    records: tuple[dict[str, Any], ...] | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class ReplaySaveResult:
    result_version: str
    status: str
    revision: int | None
    reason_codes: tuple[str, ...]


def _duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate key")
        value[key] = item
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"),
                      sort_keys=True).encode("utf-8")


def _serialize(revision: object, records: object) -> bytes | None:
    if type(revision) is not int or revision < 0 or type(records) is not list:
        return None
    if record_core.validate_snapshot(records).status != "SNAPSHOT_VALID":
        return None
    content = _canonical({
        "persistence_version": PERSISTENCE_VERSION,
        "revision": revision,
        "records": records,
    })
    return content if len(content) <= MAX_BYTES else None


def _decode(content: object) -> ReplayLoadResult:
    blocked = ReplayLoadResult(
        RESULT_VERSION, "RECOVERY_BLOCKED", None, None,
        ("REMOTE_APPROVAL_REPLAY_STORE_INVALID",),
    )
    if type(content) is not bytes or not content or len(content) > MAX_BYTES:
        return blocked
    try:
        if content.startswith(b"\xef\xbb\xbf"):
            return blocked
        value = json.loads(content.decode("utf-8"), object_pairs_hook=_duplicates)
        if type(value) is not dict or set(value) != ENVELOPE_FIELDS:
            return blocked
        if value["persistence_version"] != PERSISTENCE_VERSION:
            return blocked
        canonical = _serialize(value["revision"], value["records"])
        if canonical != content:
            return blocked
        return ReplayLoadResult(
            RESULT_VERSION, "HEALTHY", value["revision"],
            tuple(dict(record) for record in value["records"]),
            ("REMOTE_APPROVAL_REPLAY_STORE_HEALTHY",),
        )
    except Exception:
        return blocked


def _is_reparse(path: Path) -> bool:
    try:
        stat = path.lstat()
    except OSError:
        return True
    return path.is_symlink() or bool(
        getattr(stat, "st_file_attributes", 0) & _REPARSE_POINT
    )


def _safe_existing_chain(root: Path) -> bool:
    try:
        root = root.absolute()
        current = Path(root.anchor)
        for part in root.parts[1:]:
            current /= part
            if current.exists() and _is_reparse(current):
                return False
        return True
    except (OSError, RuntimeError):
        return False


def _target(record: dict[str, Any]) -> tuple[object, ...]:
    return (
        record["current_gate_id"], record["next_gate_id"],
        record["head_sha"], record["ci_run_id"],
    )


class RemoteApprovalReplayStore:
    """Shared read contract with test-only writes and no production factory."""

    def __init__(self, root: Path, token: object):
        if token not in {_TEST_TOKEN, _READ_ONLY_TOKEN}:
            raise ValueError("replay persistence activation is not authorized")
        if not isinstance(root, Path) or not root.is_absolute():
            raise ValueError("an absolute root is required")
        if not _safe_existing_chain(root):
            raise ValueError("unsafe storage root")
        self._root = root.absolute()
        self._write_enabled = token is _TEST_TOKEN
        if self._write_enabled and self._root == FORMAL_REPO_ROOT:
            raise ValueError("the formal repository cannot be a test write root")

    @classmethod
    def for_test(cls, root: Path) -> "RemoteApprovalReplayStore":
        return cls(root, _TEST_TOKEN)

    @classmethod
    def _for_read_only(cls, root: Path) -> "RemoteApprovalReplayStore":
        return cls(root, _READ_ONLY_TOKEN)

    @property
    def path(self) -> Path:
        return self._root / "runtime" / "development-remote-approval-replay-v0.1.json"

    @property
    def lock_path(self) -> Path:
        return self.path.with_suffix(".json.lock")

    @property
    def temp_path(self) -> Path:
        return self.path.with_suffix(".json.tmp")

    def _safe(self) -> bool:
        return _safe_existing_chain(self._root) and \
            _safe_existing_chain(self.path.parent)

    @contextmanager
    def _lock(self) -> Iterator[bool]:
        handle: int | None = None
        try:
            if not self._safe():
                yield False
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if not self._safe():
                yield False
                return
            handle = os.open(
                self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
            os.write(handle, b'{"lock_version":"0.1"}')
            os.fsync(handle)
            yield True
        except FileExistsError:
            yield False
        finally:
            if handle is not None:
                os.close(handle)
                try:
                    self.lock_path.unlink()
                except OSError:
                    pass

    def initialize_for_test(self) -> ReplaySaveResult:
        if not self._write_enabled:
            return ReplaySaveResult(
                RESULT_VERSION, "WRITE_DISABLED", None,
                ("PRODUCTION_REPLAY_WRITE_DISABLED",),
            )
        if self.path.exists() or not self._safe():
            return ReplaySaveResult(
                RESULT_VERSION, "RECOVERY_BLOCKED", None,
                ("TEST_REPLAY_BOOTSTRAP_REJECTED",),
            )
        content = _serialize(0, [])
        try:
            if content is None:
                raise ValueError
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            read_back = _decode(self.path.read_bytes())
            if read_back.status != "HEALTHY" or read_back.revision != 0:
                raise ValueError
            return ReplaySaveResult(
                RESULT_VERSION, "SAVED", 0, ("TEST_REPLAY_STORE_INITIALIZED",)
            )
        except Exception:
            return ReplaySaveResult(
                RESULT_VERSION, "RECOVERY_BLOCKED", None,
                ("TEST_REPLAY_BOOTSTRAP_FAILED",),
            )

    def load(self) -> ReplayLoadResult:
        try:
            if not self._safe():
                raise ValueError
            if self.lock_path.exists():
                return ReplayLoadResult(
                    RESULT_VERSION, "LOCKED", None, None,
                    ("REMOTE_APPROVAL_REPLAY_STORE_LOCKED",),
                )
            if self.temp_path.exists():
                return ReplayLoadResult(
                    RESULT_VERSION, "MANUAL_REVIEW_REQUIRED", None, None,
                    ("REMOTE_APPROVAL_REPLAY_TEMP_PRESENT",),
                )
            if not self.path.is_file():
                return ReplayLoadResult(
                    RESULT_VERSION, "MISSING_REQUIRES_BOOTSTRAP", None, None,
                    ("REMOTE_APPROVAL_REPLAY_STORE_MISSING",),
                )
            if _is_reparse(self.path) or self.path.stat().st_size > MAX_BYTES:
                raise ValueError
            return _decode(self.path.read_bytes())
        except Exception:
            return ReplayLoadResult(
                RESULT_VERSION, "RECOVERY_BLOCKED", None, None,
                ("REMOTE_APPROVAL_REPLAY_LOAD_FAILED",),
            )

    def save_record(self, record: object,
                    expected_revision: object) -> ReplaySaveResult:
        if not self._write_enabled:
            return ReplaySaveResult(
                RESULT_VERSION, "WRITE_DISABLED", None,
                ("PRODUCTION_REPLAY_WRITE_DISABLED",),
            )
        try:
            with self._lock() as acquired:
                if not acquired:
                    return ReplaySaveResult(
                        RESULT_VERSION, "LOCKED", None,
                        ("REMOTE_APPROVAL_REPLAY_STORE_LOCKED",),
                    )
                if self.temp_path.exists():
                    return ReplaySaveResult(
                        RESULT_VERSION, "MANUAL_REVIEW_REQUIRED", None,
                        ("REMOTE_APPROVAL_REPLAY_TEMP_PRESENT",),
                    )
                if not self.path.is_file():
                    return ReplaySaveResult(
                        RESULT_VERSION, "MISSING_REQUIRES_BOOTSTRAP", None,
                        ("REMOTE_APPROVAL_REPLAY_STORE_MISSING",),
                    )
                current = _decode(self.path.read_bytes())
                if current.status != "HEALTHY" or current.records is None:
                    return ReplaySaveResult(
                        RESULT_VERSION, "RECOVERY_BLOCKED", None,
                        current.reason_codes,
                    )
                if (type(expected_revision) is not int or
                        expected_revision != current.revision):
                    return ReplaySaveResult(
                        RESULT_VERSION, "STALE_REVISION", None,
                        ("STALE_REVISION",),
                    )
                if not record_core.validate_record(record):
                    return ReplaySaveResult(
                        RESULT_VERSION, "RECOVERY_BLOCKED", None,
                        ("REMOTE_APPROVAL_REPLAY_RECORD_INVALID",),
                    )
                records = [dict(value) for value in current.records]
                same_request = [
                    value for value in records
                    if value["request_id"] == record["request_id"]
                ]
                if same_request:
                    if same_request[0] == record:
                        return ReplaySaveResult(
                            RESULT_VERSION, "ALREADY_CONSUMED", current.revision,
                            ("REMOTE_APPROVAL_REPLAY_DETECTED",),
                        )
                    return ReplaySaveResult(
                        RESULT_VERSION, "RECOVERY_BLOCKED", None,
                        ("REMOTE_APPROVAL_REQUEST_ID_CONFLICT",),
                    )
                if any(_target(value) == _target(record) for value in records):
                    return ReplaySaveResult(
                        RESULT_VERSION, "RECOVERY_BLOCKED", None,
                        ("REMOTE_APPROVAL_TARGET_CONFLICT",),
                    )
                updated_revision = expected_revision + 1
                updated_records = records + [dict(record)]
                content = _serialize(updated_revision, updated_records)
                if content is None:
                    raise ValueError
                with self.temp_path.open("xb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(self.temp_path, self.path)
                read_back = _decode(self.path.read_bytes())
                if (read_back.status != "HEALTHY" or
                        read_back.revision != updated_revision or
                        read_back.records != tuple(updated_records)):
                    return ReplaySaveResult(
                        RESULT_VERSION, "RECOVERY_BLOCKED", None,
                        ("REMOTE_APPROVAL_REPLAY_READ_BACK_FAILED",),
                    )
                return ReplaySaveResult(
                    RESULT_VERSION, "SAVED", updated_revision,
                    ("REMOTE_APPROVAL_REPLAY_RECORDED_DURABLY",),
                )
        except Exception:
            return ReplaySaveResult(
                RESULT_VERSION, "RECOVERY_BLOCKED", None,
                ("REMOTE_APPROVAL_REPLAY_SAVE_FAILED",),
            )


__all__ = [
    "PERSISTENCE_VERSION", "RESULT_VERSION", "RemoteApprovalReplayStore",
    "ReplayLoadResult", "ReplaySaveResult",
]
