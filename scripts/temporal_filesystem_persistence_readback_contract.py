"""Pure contract for a future isolated temporal state filesystem boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


VERSION = "0.1-candidate"
MAX_DOCUMENT_BYTES = 1024 * 1024
MAX_WRITES_PER_RUN = 4
RETENTION_DAYS = 45


@dataclass(frozen=True)
class PersistenceReadbackEvidence:
    confined_owned_root: bool
    atomic_replace_and_exact_readback: bool
    collision_rejects_different_content: bool
    identical_replay_is_noop: bool
    uncertain_write_requires_manual_recovery: bool
    size_and_frequency_bounded: bool
    retention_is_bounded: bool


@dataclass(frozen=True)
class PersistenceReadbackContractResult:
    version: str
    status: str
    max_document_bytes: int
    max_writes_per_run: int
    retention_days: int
    filesystem_access_performed: bool
    write_authorized: bool
    connection_authorized: bool
    reason_codes: tuple[str, ...]


def evaluate(value: Any) -> PersistenceReadbackContractResult:
    ready = type(value) is PersistenceReadbackEvidence and all(
        field is True for field in (
            value.confined_owned_root,
            value.atomic_replace_and_exact_readback,
            value.collision_rejects_different_content,
            value.identical_replay_is_noop,
            value.uncertain_write_requires_manual_recovery,
            value.size_and_frequency_bounded,
            value.retention_is_bounded,
        )
    )
    return PersistenceReadbackContractResult(
        VERSION,
        "CONTRACT_READY_FOR_REVIEW" if ready else "CONTRACT_BLOCKED",
        MAX_DOCUMENT_BYTES, MAX_WRITES_PER_RUN, RETENTION_DAYS,
        False, False, False,
        ("FILESYSTEM_PERSISTENCE_READBACK_CONTRACT_DEFINED",)
        if ready else ("CONTRACT_EVIDENCE_INCOMPLETE",),
    )


__all__ = [
    "MAX_DOCUMENT_BYTES", "MAX_WRITES_PER_RUN", "RETENTION_DAYS", "VERSION",
    "PersistenceReadbackContractResult", "PersistenceReadbackEvidence", "evaluate",
]
