"""Test-root-only atomic persistence candidate for v0.2 temporal state."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from typing import Any

import temporal_filesystem_persistence_readback_contract as contract
import temporal_probe_series_state_store_candidate as plan_contract


VERSION = "0.1-candidate"


@dataclass(frozen=True)
class PersistenceResult:
    version: str
    status: str
    durable: bool
    writes_used: int
    filesystem_access_performed: bool
    production_write_authorized: bool
    reason_codes: tuple[str, ...]


def _result(status: str, writes: int, accessed: bool, *reasons: str,
            durable: bool = False) -> PersistenceResult:
    return PersistenceResult(VERSION, status, durable, writes, accessed, False,
                             tuple(reasons))


class IsolatedTemporalStateStore:
    def __init__(self, root: Path, marker: object):
        if marker is not _TEST_MARKER:
            raise ValueError("test factory required")
        self._root = root
        self._writes = 0

    @classmethod
    def for_test(cls, root: Path) -> "IsolatedTemporalStateStore":
        resolved = Path(root).resolve(strict=False)
        if not resolved.is_absolute():
            raise ValueError("absolute test root required")
        resolved.mkdir(parents=True, exist_ok=True)
        if resolved.is_symlink() or not resolved.is_dir():
            raise ValueError("unsafe test root")
        return cls(resolved, _TEST_MARKER)

    def persist(self, plan: Any, document: Any) -> PersistenceResult:
        """Persist one exact plan under the isolated root and verify read-back."""
        accessed = False
        try:
            if (type(plan) is not plan_contract.SeriesStateWritePlan
                    or plan.version != plan_contract.STORE_CANDIDATE_VERSION
                    or plan.status != plan_contract.WRITE_PLAN_READY
                    or plan.success is not True
                    or plan.filesystem_access_performed is not False
                    or plan.state_write_authorized is not False
                    or plan.reason_codes != ("MEMORY_ONLY_WRITE_PLAN",)
                    or type(document) is not bytes
                    or type(plan.filename) is not str
                    or plan_contract.STATE_FILENAME.fullmatch(plan.filename) is None
                    or type(plan.document_bytes) is not int
                    or plan.document_bytes != len(document)
                    or len(document) > contract.MAX_DOCUMENT_BYTES
                    or type(plan.document_sha256) is not str
                    or hashlib.sha256(document).hexdigest() != plan.document_sha256):
                return _result("PERSISTENCE_BLOCKED", self._writes, accessed,
                               "PLAN_OR_DOCUMENT_INVALID")
            if self._writes >= contract.MAX_WRITES_PER_RUN:
                return _result("PERSISTENCE_BLOCKED", self._writes, accessed,
                               "WRITE_FREQUENCY_LIMIT_REACHED")
            target = self._root / plan.filename
            if target.parent != self._root or target.is_symlink():
                return _result("PERSISTENCE_BLOCKED", self._writes, accessed,
                               "TARGET_BOUNDARY_INVALID")
            accessed = True
            if target.exists():
                existing = target.read_bytes()
                if existing == document:
                    return _result("IDENTICAL_REPLAY_NOOP", self._writes, True,
                                   "IDENTICAL_DOCUMENT_ALREADY_PRESENT",
                                   durable=True)
                return _result("PERSISTENCE_BLOCKED", self._writes, True,
                               "FILENAME_CONTENT_COLLISION")
            temporary = self._root / (plan.filename + ".tmp")
            if temporary.exists() or temporary.is_symlink():
                return _result("RECOVERY_REQUIRED", self._writes, True,
                               "TEMPORARY_RESIDUE_PRESENT")
            with temporary.open("xb") as stream:
                stream.write(document)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            self._writes += 1
            if target.read_bytes() != document:
                return _result("RECOVERY_REQUIRED", self._writes, True,
                               "EXACT_READBACK_FAILED")
            return _result("PERSISTED_AND_VERIFIED", self._writes, True,
                           "ATOMIC_WRITE_READBACK_VERIFIED", durable=True)
        except Exception:
            return _result("RECOVERY_REQUIRED", self._writes, accessed,
                           "PERSISTENCE_RESULT_UNCERTAIN")


_TEST_MARKER = object()

__all__ = ["IsolatedTemporalStateStore", "PersistenceResult", "VERSION"]
