"""Fail-closed gate for retaining a verified 300-item collection-only DB."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import sqlite3
from typing import Any

import revenue_mvp_expansion_page_validator as page_validator


VERSION = "0.1"
READY = "READY_FOR_COLLECTION_ONLY_RETENTION"
BLOCKED = "BLOCKED"
RETENTION_COUNT = 7
REQUIRED_TABLES = frozenset({
    "items", "item_snapshots", "collection_runs",
    "item_lifecycle_observations", "item_snapshot_titles",
})
SENSITIVE_COLUMN_TOKENS = ("api_id", "affiliate_id", "token", "secret", "password")


@dataclass(frozen=True)
class StorageBoundary:
    candidate_path: Path
    production_database_path: Path
    private_root: Path
    retention_count: int
    raw_payload_retained: bool
    publication_connected: bool
    sitemap_connected: bool
    d1_connected: bool


@dataclass(frozen=True)
class StorageDecision:
    version: str
    status: str
    item_count: int
    snapshot_count: int
    latest_run_item_count: int
    latest_run_api_calls: int
    backup_retention_count: int
    collection_only: bool
    candidate_ids_exposed: bool
    publication_allowed: bool
    production_write_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(*reasons: str) -> StorageDecision:
    return StorageDecision(
        VERSION, BLOCKED, 0, 0, 0, 0, RETENTION_COUNT, True, False, False,
        False, tuple(sorted(set(reasons))),
    )


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def assess(boundary: Any) -> StorageDecision:
    if not isinstance(boundary, StorageBoundary):
        return _blocked("BOUNDARY_INVALID")
    reasons: set[str] = set()
    candidate = boundary.candidate_path
    production = boundary.production_database_path
    private_root = boundary.private_root
    if (
        candidate.is_symlink() or production.is_symlink() or private_root.is_symlink()
        or not candidate.is_file() or not production.is_file() or not private_root.is_dir()
    ):
        reasons.add("PATH_BOUNDARY_INVALID")
    if not _inside(candidate, private_root) or candidate.resolve() == production.resolve():
        reasons.add("PRIVATE_STORAGE_BOUNDARY_INVALID")
    if candidate.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        reasons.add("CANDIDATE_DATABASE_EXTENSION_INVALID")
    if boundary.retention_count != RETENTION_COUNT:
        reasons.add("RETENTION_COUNT_INVALID")
    if boundary.raw_payload_retained:
        reasons.add("RAW_PAYLOAD_RETENTION_FORBIDDEN")
    if boundary.publication_connected or boundary.sitemap_connected or boundary.d1_connected:
        reasons.add("PUBLICATION_CONNECTION_FORBIDDEN")
    if reasons:
        return _blocked(*reasons)

    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"{candidate.resolve().as_uri()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            return _blocked("DATABASE_INTEGRITY_FAILED")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            return _blocked("DATABASE_FOREIGN_KEY_FAILED")
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        if not REQUIRED_TABLES <= tables:
            return _blocked("REQUIRED_SCHEMA_MISSING")
        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            columns = [str(row[1]).lower() for row in connection.execute(f"PRAGMA table_info({quoted})")]
            if any(token in column for column in columns for token in SENSITIVE_COLUMN_TOKENS):
                return _blocked("SENSITIVE_COLUMN_DETECTED")

        run = connection.execute(
            "SELECT * FROM collection_runs WHERE run_type='native' "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if run is None:
            return _blocked("LATEST_RUN_MISSING")
        if (
            run["status"] != "success" or run["max_items"] != 300
            or run["max_pages"] != 6 or run["api_calls"] != 6
            or run["pages_fetched"] != 6 or run["processed_items"] != 300
            or run["snapshots_inserted"] != 300
            or run["duplicate_content_ids_across_pages"] != 0
        ):
            return _blocked("LATEST_RUN_CONTRACT_INVALID")
        rows = connection.execute(
            """SELECT s.source_offset,i.content_id
               FROM item_snapshots s JOIN items i ON i.id=s.item_id
               WHERE s.collection_run_id=?
               ORDER BY s.source_offset,s.source_position,s.id""",
            (run["collection_run_id"],),
        ).fetchall()
        grouped: dict[int, list[str]] = {}
        for row in rows:
            grouped.setdefault(row["source_offset"], []).append(row["content_id"])
        pages = tuple(
            page_validator.PageObservation(offset, 50, len(values), tuple(values))
            for offset, values in sorted(grouped.items())
        )
        if page_validator.validate(pages).status != page_validator.PASS:
            return _blocked("PAGE_VALIDATION_FAILED")
        item_count = connection.execute("SELECT count(*) FROM items").fetchone()[0]
        snapshot_count = connection.execute("SELECT count(*) FROM item_snapshots").fetchone()[0]
        return StorageDecision(
            VERSION, READY, item_count, snapshot_count, 300, 6,
            RETENTION_COUNT, True, False, False, False,
            ("GIT_IGNORED_PRIVATE_STORAGE_REQUIRED", "PUBLICATION_REVIEW_SEPARATE"),
        )
    except (OSError, sqlite3.Error, ValueError):
        return _blocked("STORAGE_VALIDATION_FAILED")
    finally:
        if connection is not None:
            connection.close()


__all__ = ["StorageBoundary", "StorageDecision", "assess"]
