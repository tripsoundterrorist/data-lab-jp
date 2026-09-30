"""Atomically retain a gated expansion DB in the private collection-only area."""

from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import sqlite3
from typing import Any

import revenue_mvp_expansion_storage_gate as gate


VERSION = "0.1"
COMMITTED = "COLLECTION_ONLY_DATABASE_COMMITTED"
BLOCKED = "BLOCKED"
PRIMARY_NAME = "revenue-mvp-expansion-collection.db"
BACKUP_DIRECTORY_NAME = "revenue-mvp-expansion-backups"


@dataclass(frozen=True)
class CommitResult:
    version: str
    status: str
    candidate_sha256: str | None
    retained_sha256: str | None
    backup_created: bool
    retained_backup_count: int
    publication_allowed: bool
    production_write_performed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(reason: str) -> CommitResult:
    return CommitResult(VERSION, BLOCKED, None, None, False, 0, False, False, (reason,))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _backup_name(now: datetime, source_sha256: str) -> str:
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"expansion-{stamp}-{source_sha256[:12]}.db"


def _validated_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(
        (
            path for path in directory.glob("expansion-*.db")
            if path.is_file() and not path.is_symlink()
        ),
        key=lambda path: path.name,
        reverse=True,
    )


def commit(
    staged_candidate: Path,
    production_database: Path,
    private_root: Path,
    *,
    expected_candidate_sha256: str,
    committed_at: datetime,
) -> CommitResult:
    try:
        destination = private_root / PRIMARY_NAME
        backups = private_root / BACKUP_DIRECTORY_NAME
        if (
            committed_at.tzinfo is None
            or staged_candidate.is_symlink() or production_database.is_symlink()
            or private_root.is_symlink() or not staged_candidate.is_file()
            or not production_database.is_file() or not private_root.is_dir()
            or len(expected_candidate_sha256) != 64
            or any(character not in "0123456789abcdef" for character in expected_candidate_sha256)
        ):
            return _blocked("INPUT_BOUNDARY_INVALID")
        try:
            staged_candidate.resolve().relative_to(private_root.resolve())
        except ValueError:
            return _blocked("STAGED_CANDIDATE_OUTSIDE_PRIVATE_ROOT")
        if staged_candidate.resolve() == destination.resolve():
            return _blocked("STAGED_CANDIDATE_IS_DESTINATION")
        candidate_sha = _sha256(staged_candidate)
        if candidate_sha != expected_candidate_sha256:
            return _blocked("CANDIDATE_IDENTITY_MISMATCH")
        decision = gate.assess(gate.StorageBoundary(
            candidate_path=staged_candidate,
            production_database_path=production_database,
            private_root=private_root,
            retention_count=gate.RETENTION_COUNT,
            raw_payload_retained=False,
            publication_connected=False,
            sitemap_connected=False,
            d1_connected=False,
        ))
        if decision.status != gate.READY:
            return _blocked("STORAGE_GATE_BLOCKED")

        backup_created = False
        if destination.exists():
            if destination.is_symlink() or not destination.is_file():
                return _blocked("EXISTING_DESTINATION_INVALID")
            old_sha = _sha256(destination)
            backups.mkdir(parents=False, exist_ok=True)
            backup_path = backups / _backup_name(committed_at, old_sha)
            temporary_backup = backup_path.with_suffix(".db.tmp")
            if backup_path.exists() or temporary_backup.exists():
                return _blocked("BACKUP_COLLISION")
            with closing(sqlite3.connect(f"{destination.resolve().as_uri()}?mode=ro", uri=True)) as source:
                source.execute("PRAGMA query_only=ON")
                with closing(sqlite3.connect(temporary_backup)) as target:
                    source.backup(target, pages=256, sleep=0.05)
            if _sha256(temporary_backup) == "":
                return _blocked("BACKUP_IDENTITY_INVALID")
            temporary_backup.replace(backup_path)
            backup_created = True

        os.replace(staged_candidate, destination)
        if _sha256(destination) != candidate_sha:
            return _blocked("RETAINED_IDENTITY_MISMATCH")
        existing = _validated_files(backups)
        for obsolete in existing[gate.RETENTION_COUNT:]:
            obsolete.unlink()
        return CommitResult(
            VERSION, COMMITTED, candidate_sha, candidate_sha, backup_created,
            len(_validated_files(backups)), False, False,
            ("COLLECTION_ONLY", "PUBLICATION_REVIEW_SEPARATE"),
        )
    except (OSError, sqlite3.Error, ValueError):
        return _blocked("STORAGE_COMMIT_FAILED")


__all__ = ["CommitResult", "commit"]
