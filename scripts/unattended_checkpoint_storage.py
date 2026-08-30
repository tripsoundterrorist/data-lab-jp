"""Fail-closed checkpoint object storage for Queue Persistence v0.1.

Phase A/B exposes only an explicitly test-scoped filesystem store.  It never
selects a checkpoint, mutates Queue state, resumes a job, or deletes an object.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable

import unattended_job_queue as core


CHECKPOINT_STORAGE_VERSION = "0.1"
CHECKPOINT_RESULT_VERSION = "0.1"
MAX_CHECKPOINT_BYTES = 1024 * 1024
STORAGE_ID = re.compile(r"[0-9a-f]{64}\Z")
_ENVELOPE_FIELDS = {"checkpoint_storage_version", "queue_id", "checkpoint"}
_CHECKPOINT_FIELDS = {
    "job_id", "state", "last_completed_step", "resume_preconditions",
    "blocker_codes", "attempt_count", "checkpoint_time", "reason_codes",
}
_REPARSE_POINT = 0x400
_TEST_TOKEN = object()
_READ_ONLY_TOKEN = object()
FORMAL_REPO_ROOT = Path(__file__).resolve().parents[1]


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


def _checkpoint_dict(checkpoint: core.Checkpoint) -> dict[str, Any]:
    return checkpoint.to_dict()


def _checkpoint_from_dict(value: Any) -> core.Checkpoint | None:
    if type(value) is not dict or set(value) != _CHECKPOINT_FIELDS:
        return None
    if not all(type(value[name]) is list for name in
               ("resume_preconditions", "blocker_codes", "reason_codes")):
        return None
    try:
        checkpoint = core.Checkpoint(
            job_id=value["job_id"], state=value["state"],
            last_completed_step=value["last_completed_step"],
            resume_preconditions=tuple(value["resume_preconditions"]),
            blocker_codes=tuple(value["blocker_codes"]),
            attempt_count=value["attempt_count"],
            checkpoint_time=value["checkpoint_time"],
            reason_codes=tuple(value["reason_codes"]),
        )
    except (KeyError, TypeError, ValueError):
        return None
    return checkpoint if core.validate_checkpoint(checkpoint)[0] else None


def checkpoint_object_bytes(identity: core.QueueIdentity,
                            checkpoint: core.Checkpoint) -> bytes | None:
    if not core.validate_queue_identity(identity):
        return None
    if not core.validate_checkpoint(checkpoint)[0]:
        return None
    content = _canonical({
        "checkpoint_storage_version": CHECKPOINT_STORAGE_VERSION,
        "queue_id": identity.queue_id,
        "checkpoint": _checkpoint_dict(checkpoint),
    })
    return content if len(content) <= MAX_CHECKPOINT_BYTES else None


def checkpoint_storage_id(content: bytes) -> str | None:
    if type(content) is not bytes or not content or len(content) > MAX_CHECKPOINT_BYTES:
        return None
    return hashlib.sha256(content).hexdigest()


def _is_reparse(path: Path) -> bool:
    try:
        stat = path.lstat()
    except OSError:
        return True
    return path.is_symlink() or bool(getattr(stat, "st_file_attributes", 0) & _REPARSE_POINT)


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


@dataclass(frozen=True)
class CheckpointSaveResult:
    result_version: str
    status: str
    checkpoint_storage_id: str | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class CheckpointLoadResult:
    result_version: str
    status: str
    checkpoint: core.Checkpoint | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class CheckpointInspectionResult:
    result_version: str
    status: str
    checkpoint_object_count: int | None
    unreferenced_object_count: int | None
    confirmed_orphan_count: int | None
    corrupt_active_count: int | None
    corrupt_unreferenced_count: int | None
    temp_artifact_detected: bool | None
    action_required: str
    reason_codes: tuple[str, ...]


class CheckpointStorage:
    """Shared validator with test-write and production-read-only modes."""

    def __init__(self, root: Path, identity: core.QueueIdentity, token: object):
        if token not in {_TEST_TOKEN, _READ_ONLY_TOKEN}:
            raise ValueError("checkpoint storage activation is not authorized")
        if not isinstance(root, Path) or root.is_absolute() is False:
            raise ValueError("an absolute temporary root is required")
        if not core.validate_queue_identity(identity) or not _safe_existing_chain(root):
            raise ValueError("unsafe storage root or identity")
        self._root = root.absolute()
        self._identity = identity
        self._write_enabled = token is _TEST_TOKEN
        if self._write_enabled and self._root == FORMAL_REPO_ROOT:
            raise ValueError("the formal production root cannot be a test write root")

    @classmethod
    def for_test(cls, root: Path, identity: core.QueueIdentity) -> "CheckpointStorage":
        return cls(root, identity, _TEST_TOKEN)

    @classmethod
    def _for_read_only(cls, root: Path, identity: core.QueueIdentity) -> "CheckpointStorage":
        return cls(root, identity, _READ_ONLY_TOKEN)

    @property
    def objects_dir(self) -> Path:
        return self._root / "runtime" / "checkpoints" / self._identity.queue_id / "objects"

    def _safe(self) -> bool:
        return _safe_existing_chain(self._root) and _safe_existing_chain(self.objects_dir)

    def _object_path(self, storage_id: str) -> Path | None:
        if type(storage_id) is not str or STORAGE_ID.fullmatch(storage_id) is None:
            return None
        candidate = self.objects_dir / f"{storage_id}.json"
        try:
            if candidate.parent.absolute() != self.objects_dir.absolute():
                return None
        except (OSError, RuntimeError):
            return None
        return candidate

    def save_checkpoint(self, checkpoint: core.Checkpoint) -> CheckpointSaveResult:
        if not self._write_enabled:
            return CheckpointSaveResult(CHECKPOINT_RESULT_VERSION, "WRITE_DISABLED", None,
                                        ("PRODUCTION_CHECKPOINT_WRITE_DISABLED",))
        invalid = CheckpointSaveResult(CHECKPOINT_RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                       ("CHECKPOINT_INVALID",))
        try:
            content = checkpoint_object_bytes(self._identity, checkpoint)
            if content is None or not self._safe():
                return invalid
            storage_id = checkpoint_storage_id(content)
            if storage_id is None:
                return invalid
            self.objects_dir.mkdir(parents=True, exist_ok=True)
            if not self._safe():
                return invalid
            final = self._object_path(storage_id)
            if final is None:
                return invalid
            if final.exists():
                existing = final.read_bytes()
                if existing == content:
                    loaded = self.load_checkpoint(storage_id, checkpoint.job_id)
                    if loaded.status == "HEALTHY":
                        return CheckpointSaveResult(CHECKPOINT_RESULT_VERSION, "NO_CHANGE",
                                                    storage_id, ("CHECKPOINT_ALREADY_STORED",))
                return CheckpointSaveResult(CHECKPOINT_RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                            ("CHECKPOINT_OBJECT_CONFLICT",))
            temp = final.with_suffix(".json.tmp")
            if temp.exists():
                return CheckpointSaveResult(CHECKPOINT_RESULT_VERSION, "MANUAL_REVIEW_REQUIRED", None,
                                            ("CHECKPOINT_TEMP_ARTIFACT_PRESENT",))
            with temp.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, final)
            loaded = self.load_checkpoint(storage_id, checkpoint.job_id)
            if loaded.status != "HEALTHY":
                return CheckpointSaveResult(CHECKPOINT_RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                            ("CHECKPOINT_READ_BACK_FAILED",))
            return CheckpointSaveResult(CHECKPOINT_RESULT_VERSION, "SAVED", storage_id,
                                        ("CHECKPOINT_STORED",))
        except Exception:
            return invalid

    def load_checkpoint(self, storage_id: str, expected_job_id: str) -> CheckpointLoadResult:
        blocked = CheckpointLoadResult(CHECKPOINT_RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                       ("CHECKPOINT_OBJECT_INVALID",))
        try:
            path = self._object_path(storage_id)
            if path is None or not self._safe():
                return blocked
            if not path.is_file():
                return CheckpointLoadResult(CHECKPOINT_RESULT_VERSION, "REFERENCE_MISSING", None,
                                            ("REFERENCE_MISSING",))
            if _is_reparse(path) or path.stat().st_size > MAX_CHECKPOINT_BYTES:
                return blocked
            content = path.read_bytes()
            if checkpoint_storage_id(content) != storage_id:
                return CheckpointLoadResult(CHECKPOINT_RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                            ("CHECKPOINT_DIGEST_MISMATCH",))
            value = json.loads(content.decode("utf-8-sig"), object_pairs_hook=_duplicates)
            if content.startswith(b"\xef\xbb\xbf") or type(value) is not dict or set(value) != _ENVELOPE_FIELDS:
                return blocked
            if value["checkpoint_storage_version"] != CHECKPOINT_STORAGE_VERSION:
                return blocked
            if value["queue_id"] != self._identity.queue_id:
                return CheckpointLoadResult(CHECKPOINT_RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                            ("REFERENCE_QUEUE_MISMATCH",))
            checkpoint = _checkpoint_from_dict(value["checkpoint"])
            if checkpoint is None:
                return blocked
            if checkpoint.job_id != expected_job_id:
                return CheckpointLoadResult(CHECKPOINT_RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                            ("REFERENCE_JOB_MISMATCH",))
            if checkpoint_object_bytes(self._identity, checkpoint) != content:
                return blocked
            return CheckpointLoadResult(CHECKPOINT_RESULT_VERSION, "HEALTHY", checkpoint,
                                        ("CHECKPOINT_OBJECT_VALID",))
        except Exception:
            return blocked

    def inspect(self, active_ids: Iterable[str] = ()) -> CheckpointInspectionResult:
        try:
            active = frozenset(active_ids)
            if any(STORAGE_ID.fullmatch(value) is None for value in active) or not self._safe():
                raise ValueError
            if not self.objects_dir.exists():
                if active:
                    return CheckpointInspectionResult(
                        CHECKPOINT_RESULT_VERSION, "RECOVERY_BLOCKED", 0, 0, None,
                        0, 0, False, "STOP_QUEUE_RECOVERY", ("REFERENCE_MISSING",))
                return CheckpointInspectionResult(
                    CHECKPOINT_RESULT_VERSION, "MISSING_EMPTY_STORAGE_ALLOWED", 0, 0, None,
                    0, 0, False, "NONE", ("CHECKPOINT_STORAGE_ABSENT",))
            temps = list(self.objects_dir.glob("*.tmp"))
            objects = list(self.objects_dir.glob("*.json"))
            corrupt_active = corrupt_unreferenced = 0
            valid_names: set[str] = set()
            present_names = {path.stem for path in objects}
            for path in objects:
                storage_id = path.stem
                structural = STORAGE_ID.fullmatch(storage_id) is not None
                if structural:
                    try:
                        content = path.read_bytes()
                        value = json.loads(content.decode("utf-8-sig"), object_pairs_hook=_duplicates)
                        cp = _checkpoint_from_dict(value.get("checkpoint")) if type(value) is dict else None
                        structural = (set(value) == _ENVELOPE_FIELDS
                                      and value["checkpoint_storage_version"] == CHECKPOINT_STORAGE_VERSION
                                      and value["queue_id"] == self._identity.queue_id
                                      and cp is not None
                                      and checkpoint_storage_id(content) == storage_id
                                      and checkpoint_object_bytes(self._identity, cp) == content)
                    except Exception:
                        structural = False
                if structural:
                    valid_names.add(storage_id)
                elif storage_id in active:
                    corrupt_active += 1
                else:
                    corrupt_unreferenced += 1
            missing = len(active - present_names)
            unreferenced = len(valid_names - active)
            if corrupt_active or missing:
                status, action = "RECOVERY_BLOCKED", "STOP_QUEUE_RECOVERY"
            elif temps or corrupt_unreferenced:
                status, action = "MANUAL_REVIEW_REQUIRED", "REVIEW_CHECKPOINT_STORAGE"
            elif unreferenced:
                status, action = "UNREFERENCED_OBJECTS_PRESENT", "NONE"
            else:
                status, action = "HEALTHY", "NONE"
            reasons = [status]
            if missing:
                reasons.append("REFERENCE_MISSING")
            return CheckpointInspectionResult(
                CHECKPOINT_RESULT_VERSION, status, len(objects), unreferenced, None,
                corrupt_active, corrupt_unreferenced, bool(temps), action, tuple(reasons))
        except Exception:
            return CheckpointInspectionResult(
                CHECKPOINT_RESULT_VERSION, "RECOVERY_BLOCKED", None, None, None,
                None, None, None, "STOP_QUEUE_RECOVERY", ("CHECKPOINT_INSPECTION_FAILED",))


__all__ = [
    "CHECKPOINT_STORAGE_VERSION", "FORMAL_REPO_ROOT", "MAX_CHECKPOINT_BYTES", "CheckpointInspectionResult",
    "CheckpointLoadResult", "CheckpointSaveResult", "CheckpointStorage",
    "checkpoint_object_bytes", "checkpoint_storage_id",
]
