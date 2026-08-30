"""Strict Queue Persistence v0.1 schema and temporary-root Phase B store."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import re
from typing import Any, Iterator

import unattended_job_queue as core
from unattended_checkpoint_storage import CheckpointStorage


PERSISTENCE_VERSION = "0.1"
REFERENCE_VERSION = "0.1"
RESULT_VERSION = "0.1"
MAX_QUEUE_BYTES = 16 * 1024 * 1024
STORAGE_ID = re.compile(r"[0-9a-f]{64}\Z")
_ENVELOPE_FIELDS = {
    "persistence_version", "queue_version", "queue_id", "revision", "jobs",
    "active_checkpoint_refs",
}
_JOB_FIELDS = {
    "queue_version", "job_id", "job_type", "priority", "risk_class",
    "dependencies", "blocker_codes", "requires_approval", "retry_policy",
    "max_attempts", "checkpoint_supported", "created_at", "deadline_class",
    "state", "attempt_count", "approval_received",
}
_REFERENCE_FIELDS = {"reference_version", "job_id", "checkpoint_storage_id"}
_REPARSE_POINT = 0x400
_TEST_TOKEN = object()


def _duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate key")
        value[key] = item
    return value


@dataclass(frozen=True)
class ActiveCheckpointReference:
    reference_version: str
    job_id: str
    checkpoint_storage_id: str

    def to_dict(self) -> dict[str, str]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class PersistedQueueSnapshot:
    queue_identity: core.QueueIdentity
    revision: int
    jobs: tuple[core.JobContract, ...]
    active_checkpoint_refs: tuple[ActiveCheckpointReference, ...]


@dataclass(frozen=True)
class QueueLoadResult:
    result_version: str
    status: str
    snapshot: PersistedQueueSnapshot | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class QueueSaveResult:
    result_version: str
    status: str
    revision: int | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class ReferenceUpdateResult:
    result_version: str
    status: str
    snapshot: PersistedQueueSnapshot | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class QueueInspectionResult:
    result_version: str
    status: str
    persistence_version: str | None
    queue_id: str | None
    revision: int | None
    job_count: int | None
    state_counts: tuple[tuple[str, int], ...]
    active_reference_count: int | None
    lock_status: str
    temp_status: str
    action_required: str
    reason_codes: tuple[str, ...]


def validate_active_checkpoint_refs(
    refs: Any, jobs: tuple[core.JobContract, ...]
) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    if type(refs) is not tuple or any(type(ref) is not ActiveCheckpointReference for ref in refs):
        return False, ("ACTIVE_REFERENCE_SCHEMA_INVALID",)
    ids = [job.job_id for job in jobs]
    ref_ids = [ref.job_id for ref in refs]
    if ref_ids != sorted(ref_ids):
        reasons.append("ACTIVE_REFERENCE_ORDER_INVALID")
    if len(ref_ids) != len(set(ref_ids)):
        reasons.append("ACTIVE_REFERENCE_DUPLICATE")
    if any(ref.job_id not in ids for ref in refs):
        reasons.append("ORPHAN_REFERENCE")
    for ref in refs:
        if (set(vars(ref)) != _REFERENCE_FIELDS
                or ref.reference_version != REFERENCE_VERSION
                or type(ref.job_id) is not str
                or type(ref.checkpoint_storage_id) is not str
                or STORAGE_ID.fullmatch(ref.checkpoint_storage_id) is None):
            reasons.append("ACTIVE_REFERENCE_SCHEMA_INVALID")
    return not reasons, tuple(sorted(set(reasons)))


def validate_snapshot(snapshot: Any) -> tuple[bool, tuple[str, ...]]:
    if type(snapshot) is not PersistedQueueSnapshot:
        return False, ("PERSISTED_SNAPSHOT_INVALID",)
    reasons: list[str] = []
    if not core.validate_queue_identity(snapshot.queue_identity):
        reasons.append("QUEUE_IDENTITY_INVALID")
    if type(snapshot.revision) is not int or snapshot.revision < 0:
        reasons.append("REVISION_INVALID")
    if type(snapshot.jobs) is not tuple:
        reasons.append("QUEUE_JOBS_INVALID")
    else:
        valid, queue_reasons = core.validate_queue(snapshot.jobs)
        if not valid:
            reasons.extend(queue_reasons)
    if type(snapshot.active_checkpoint_refs) is not tuple:
        reasons.append("ACTIVE_REFERENCE_SCHEMA_INVALID")
    elif type(snapshot.jobs) is tuple:
        valid, ref_reasons = validate_active_checkpoint_refs(snapshot.active_checkpoint_refs,
                                                             snapshot.jobs)
        if not valid:
            reasons.extend(ref_reasons)
    return not reasons, tuple(sorted(set(reasons)))


def _job_dict(job: core.JobContract) -> dict[str, Any]:
    return {
        "queue_version": job.queue_version, "job_id": job.job_id,
        "job_type": job.job_type, "priority": job.priority,
        "risk_class": job.risk_class, "dependencies": list(job.dependencies),
        "blocker_codes": list(job.blocker_codes),
        "requires_approval": job.requires_approval,
        "retry_policy": job.retry_policy, "max_attempts": job.max_attempts,
        "checkpoint_supported": job.checkpoint_supported,
        "created_at": job.created_at, "deadline_class": job.deadline_class,
        "state": job.state, "attempt_count": job.attempt_count,
        "approval_received": job.approval_received,
    }


def _job_from_dict(value: Any) -> core.JobContract | None:
    if type(value) is not dict or set(value) != _JOB_FIELDS:
        return None
    if type(value["dependencies"]) is not list or type(value["blocker_codes"]) is not list:
        return None
    try:
        job = core.JobContract(
            queue_version=value["queue_version"], job_id=value["job_id"],
            job_type=value["job_type"], priority=value["priority"],
            risk_class=value["risk_class"], dependencies=tuple(value["dependencies"]),
            blocker_codes=tuple(value["blocker_codes"]),
            requires_approval=value["requires_approval"], retry_policy=value["retry_policy"],
            max_attempts=value["max_attempts"],
            checkpoint_supported=value["checkpoint_supported"],
            created_at=value["created_at"], deadline_class=value["deadline_class"],
            state=value["state"], attempt_count=value["attempt_count"],
            approval_received=value["approval_received"],
        )
    except (KeyError, TypeError, ValueError):
        return None
    return job if core.validate_job(job)[0] else None


def serialize_queue(snapshot: PersistedQueueSnapshot) -> bytes | None:
    valid, _ = validate_snapshot(snapshot)
    if not valid:
        return None
    value = {
        "persistence_version": PERSISTENCE_VERSION,
        "queue_version": core.QUEUE_VERSION,
        "queue_id": snapshot.queue_identity.queue_id,
        "revision": snapshot.revision,
        "jobs": [_job_dict(job) for job in snapshot.jobs],
        "active_checkpoint_refs": [ref.to_dict() for ref in snapshot.active_checkpoint_refs],
    }
    content = json.dumps(value, ensure_ascii=True, separators=(",", ":"),
                         sort_keys=True).encode("utf-8")
    return content if len(content) <= MAX_QUEUE_BYTES else None


def deserialize_queue(content: bytes) -> QueueLoadResult:
    blocked = QueueLoadResult(RESULT_VERSION, "RECOVERY_BLOCKED", None,
                              ("QUEUE_DOCUMENT_INVALID",))
    try:
        if type(content) is not bytes or not content or len(content) > MAX_QUEUE_BYTES:
            return blocked
        if content.startswith(b"\xef\xbb\xbf") or content.endswith(b"\n") or content.endswith(b"\r"):
            return blocked
        value = json.loads(content.decode("utf-8"), object_pairs_hook=_duplicates)
        if type(value) is not dict or set(value) != _ENVELOPE_FIELDS:
            return blocked
        if value["persistence_version"] != PERSISTENCE_VERSION:
            return QueueLoadResult(RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                   ("PERSISTENCE_VERSION_UNSUPPORTED",))
        if value["queue_version"] != core.QUEUE_VERSION:
            return QueueLoadResult(RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                   ("QUEUE_VERSION_UNSUPPORTED",))
        identity = core.QueueIdentity(core.IDENTITY_CONTRACT_VERSION, value["queue_id"],
                                      "CONFIGURED", "POLICY_BACKED_LOGICAL_IDENTITY")
        if not core.validate_queue_identity(identity):
            return QueueLoadResult(RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                   ("QUEUE_IDENTITY_INVALID",))
        if type(value["revision"]) is not int or value["revision"] < 0:
            return QueueLoadResult(RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                   ("REVISION_INVALID",))
        if type(value["jobs"]) is not list or type(value["active_checkpoint_refs"]) is not list:
            return blocked
        jobs = tuple(_job_from_dict(item) for item in value["jobs"])
        if any(job is None for job in jobs):
            return blocked
        refs: list[ActiveCheckpointReference] = []
        for item in value["active_checkpoint_refs"]:
            if type(item) is not dict or set(item) != _REFERENCE_FIELDS:
                return blocked
            refs.append(ActiveCheckpointReference(item["reference_version"], item["job_id"],
                                                  item["checkpoint_storage_id"]))
        snapshot = PersistedQueueSnapshot(identity, value["revision"], jobs, tuple(refs))
        valid, reasons = validate_snapshot(snapshot)
        if not valid:
            return QueueLoadResult(RESULT_VERSION, "RECOVERY_BLOCKED", None, reasons)
        if serialize_queue(snapshot) != content:
            return QueueLoadResult(RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                   ("QUEUE_CANONICAL_ENCODING_REQUIRED",))
        return QueueLoadResult(RESULT_VERSION, "HEALTHY", snapshot, ("QUEUE_LOADED",))
    except Exception:
        return blocked


def replace_active_checkpoint_ref(
    snapshot: PersistedQueueSnapshot, job_id: str, checkpoint_storage_id: str
) -> ReferenceUpdateResult:
    valid, reasons = validate_snapshot(snapshot)
    if not valid or job_id not in {job.job_id for job in snapshot.jobs}:
        return ReferenceUpdateResult(RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                     reasons or ("REFERENCE_JOB_UNKNOWN",))
    if type(checkpoint_storage_id) is not str or STORAGE_ID.fullmatch(checkpoint_storage_id) is None:
        return ReferenceUpdateResult(RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                     ("CHECKPOINT_STORAGE_ID_INVALID",))
    current = {ref.job_id: ref for ref in snapshot.active_checkpoint_refs}
    if job_id in current and current[job_id].checkpoint_storage_id == checkpoint_storage_id:
        return ReferenceUpdateResult(RESULT_VERSION, "NO_CHANGE", snapshot,
                                     ("ACTIVE_REFERENCE_UNCHANGED",))
    current[job_id] = ActiveCheckpointReference(REFERENCE_VERSION, job_id,
                                                checkpoint_storage_id)
    updated = replace(snapshot, active_checkpoint_refs=tuple(current[key] for key in sorted(current)))
    return ReferenceUpdateResult(RESULT_VERSION, "UPDATED", updated,
                                 ("ACTIVE_REFERENCE_REPLACED",))


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


class QueuePersistenceStore:
    """Temporary-root Queue store; production roots remain unavailable in Phase A/B."""

    def __init__(self, root: Path, checkpoint_storage: CheckpointStorage | None, token: object):
        if token is not _TEST_TOKEN or not isinstance(root, Path) or not root.is_absolute():
            raise ValueError("production storage is not enabled in Phase A/B")
        if not _safe_existing_chain(root):
            raise ValueError("unsafe temporary root")
        self._root = root.absolute()
        self._checkpoint_storage = checkpoint_storage

    @classmethod
    def for_test(cls, root: Path, checkpoint_storage: CheckpointStorage | None = None
                 ) -> "QueuePersistenceStore":
        return cls(root, checkpoint_storage, _TEST_TOKEN)

    @property
    def queue_path(self) -> Path:
        return self._root / "runtime" / "unattended-queue-v0.1.json"

    @property
    def lock_path(self) -> Path:
        return self.queue_path.with_suffix(".json.lock")

    @property
    def temp_path(self) -> Path:
        return self.queue_path.with_suffix(".json.tmp")

    def _safe(self) -> bool:
        return _safe_existing_chain(self._root) and _safe_existing_chain(self.queue_path.parent)

    @contextmanager
    def _lock(self) -> Iterator[bool]:
        handle: int | None = None
        try:
            if not self._safe():
                yield False
                return
            self.queue_path.parent.mkdir(parents=True, exist_ok=True)
            if not self._safe():
                yield False
                return
            handle = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
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

    def initialize_for_test(self, snapshot: PersistedQueueSnapshot) -> QueueSaveResult:
        """Explicit test fixture bootstrap; impossible on a production store."""
        if snapshot.revision != 0 or self.queue_path.exists() or not self._safe():
            return QueueSaveResult(RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                   ("TEST_BOOTSTRAP_REJECTED",))
        content = serialize_queue(snapshot)
        if content is None:
            return QueueSaveResult(RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                   ("PERSISTED_SNAPSHOT_INVALID",))
        try:
            self.queue_path.parent.mkdir(parents=True, exist_ok=True)
            with self.queue_path.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            return QueueSaveResult(RESULT_VERSION, "SAVED", 0, ("TEST_QUEUE_INITIALIZED",))
        except Exception:
            return QueueSaveResult(RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                   ("TEST_BOOTSTRAP_FAILED",))

    def load_queue(self, *, validate_active_objects: bool = True) -> QueueLoadResult:
        try:
            if not self._safe():
                return QueueLoadResult(RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                       ("QUEUE_PATH_UNSAFE",))
            if self.lock_path.exists():
                return QueueLoadResult(RESULT_VERSION, "LOCKED", None, ("QUEUE_LOCKED",))
            if self.temp_path.exists():
                return QueueLoadResult(RESULT_VERSION, "MANUAL_REVIEW_REQUIRED", None,
                                       ("QUEUE_TEMP_ARTIFACT_PRESENT",))
            if not self.queue_path.is_file():
                return QueueLoadResult(RESULT_VERSION, "MISSING_REQUIRES_BOOTSTRAP", None,
                                       ("QUEUE_FILE_MISSING",))
            if _is_reparse(self.queue_path) or self.queue_path.stat().st_size > MAX_QUEUE_BYTES:
                return QueueLoadResult(RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                       ("QUEUE_PATH_UNSAFE",))
            result = deserialize_queue(self.queue_path.read_bytes())
            if result.status != "HEALTHY" or not validate_active_objects:
                return result
            if self._checkpoint_storage is None and result.snapshot.active_checkpoint_refs:
                return QueueLoadResult(RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                       ("CHECKPOINT_STORAGE_REQUIRED",))
            for ref in result.snapshot.active_checkpoint_refs:
                loaded = self._checkpoint_storage.load_checkpoint(
                    ref.checkpoint_storage_id, ref.job_id)
                if loaded.status != "HEALTHY":
                    return QueueLoadResult(RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                           loaded.reason_codes)
            return result
        except Exception:
            return QueueLoadResult(RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                   ("QUEUE_LOAD_FAILED",))

    def save_queue(self, snapshot: PersistedQueueSnapshot,
                   expected_revision: int) -> QueueSaveResult:
        try:
            with self._lock() as acquired:
                if not acquired:
                    return QueueSaveResult(RESULT_VERSION, "LOCKED", None, ("QUEUE_LOCKED",))
                if self.temp_path.exists():
                    return QueueSaveResult(RESULT_VERSION, "MANUAL_REVIEW_REQUIRED", None,
                                           ("QUEUE_TEMP_ARTIFACT_PRESENT",))
                if not self.queue_path.is_file():
                    return QueueSaveResult(RESULT_VERSION, "MISSING_REQUIRES_BOOTSTRAP", None,
                                           ("QUEUE_FILE_MISSING",))
                current = deserialize_queue(self.queue_path.read_bytes())
                if current.status != "HEALTHY":
                    return QueueSaveResult(RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                           current.reason_codes)
                if (type(expected_revision) is not int
                        or current.snapshot.revision != expected_revision
                        or snapshot.revision != expected_revision):
                    return QueueSaveResult(RESULT_VERSION, "STALE_REVISION", None,
                                           ("STALE_REVISION",))
                if snapshot.active_checkpoint_refs and self._checkpoint_storage is None:
                    return QueueSaveResult(RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                           ("CHECKPOINT_STORAGE_REQUIRED",))
                for ref in snapshot.active_checkpoint_refs:
                    loaded = self._checkpoint_storage.load_checkpoint(
                        ref.checkpoint_storage_id, ref.job_id)
                    if loaded.status != "HEALTHY":
                        return QueueSaveResult(RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                               loaded.reason_codes)
                updated = replace(snapshot, revision=expected_revision + 1)
                content = serialize_queue(updated)
                if content is None:
                    return QueueSaveResult(RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                           ("PERSISTED_SNAPSHOT_INVALID",))
                with self.temp_path.open("xb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(self.temp_path, self.queue_path)
                read_back = deserialize_queue(self.queue_path.read_bytes())
                if read_back.status != "HEALTHY" or read_back.snapshot != updated:
                    return QueueSaveResult(RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                           ("QUEUE_READ_BACK_FAILED",))
                return QueueSaveResult(RESULT_VERSION, "SAVED", updated.revision,
                                       ("QUEUE_SAVED",))
        except Exception:
            return QueueSaveResult(RESULT_VERSION, "RECOVERY_BLOCKED", None,
                                   ("QUEUE_SAVE_FAILED",))

    def inspect_queue_storage(self) -> QueueInspectionResult:
        lock = "PRESENT" if self.lock_path.exists() else "ABSENT"
        temp = "PRESENT" if self.temp_path.exists() else "ABSENT"
        result = self.load_queue(validate_active_objects=False)
        snapshot = result.snapshot
        if snapshot is None:
            return QueueInspectionResult(
                RESULT_VERSION, result.status, None, None, None, None, (), None,
                lock, temp, "OPERATOR_REVIEW" if result.status != "HEALTHY" else "NONE",
                result.reason_codes)
        counts: dict[str, int] = {}
        for job in snapshot.jobs:
            counts[job.state] = counts.get(job.state, 0) + 1
        status, reasons = result.status, list(result.reason_codes)
        if any(job.state == core.CHECKPOINTED for job in snapshot.jobs
               if job.job_id not in {ref.job_id for ref in snapshot.active_checkpoint_refs}):
            status = "MANUAL_REVIEW_REQUIRED"
            reasons.append("CHECKPOINTED_REFERENCE_ABSENT")
        return QueueInspectionResult(
            RESULT_VERSION, status, PERSISTENCE_VERSION, snapshot.queue_identity.queue_id,
            snapshot.revision, len(snapshot.jobs), tuple(sorted(counts.items())),
            len(snapshot.active_checkpoint_refs), lock, temp,
            "OPERATOR_REVIEW" if status != "HEALTHY" else "NONE", tuple(reasons))


__all__ = [
    "MAX_QUEUE_BYTES", "PERSISTENCE_VERSION", "REFERENCE_VERSION",
    "ActiveCheckpointReference", "PersistedQueueSnapshot", "QueueInspectionResult",
    "QueueLoadResult", "QueuePersistenceStore", "QueueSaveResult",
    "ReferenceUpdateResult", "deserialize_queue", "replace_active_checkpoint_ref",
    "serialize_queue", "validate_active_checkpoint_refs", "validate_snapshot",
]
