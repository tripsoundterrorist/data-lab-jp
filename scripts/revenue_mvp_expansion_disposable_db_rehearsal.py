"""Rehearse an isolated SQLite copy and restore without retaining either file."""

from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from typing import Any


VERSION = "0.1"
VERIFIED = "DISPOSABLE_DATABASE_REHEARSAL_VERIFIED"
BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class RehearsalResult:
    version: str
    status: str
    source_sha256: str | None
    table_count: int
    item_count: int
    snapshot_count: int
    collection_run_count: int
    logical_digest_match: bool
    source_identity_preserved: bool
    temporary_files_retained: bool
    production_write_performed: bool
    api_calls: int
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(reason: str) -> RehearsalResult:
    return RehearsalResult(
        VERSION, BLOCKED, None, 0, 0, 0, 0, False, False, False, False, 0,
        (reason,),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only = ON")
    return connection


def _state(connection: sqlite3.Connection) -> tuple[str, int, int, int, int]:
    if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
        raise ValueError("INTEGRITY_FAILED")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise ValueError("FOREIGN_KEY_FAILED")
    tables = tuple(
        row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    )
    if not tables:
        raise ValueError("SCHEMA_EMPTY")
    digest = hashlib.sha256()
    for table in tables:
        quoted = '"' + table.replace('"', '""') + '"'
        digest.update(table.encode("utf-8"))
        for row in connection.execute(f"SELECT * FROM {quoted} ORDER BY rowid"):
            digest.update(repr(tuple(row)).encode("utf-8"))
            digest.update(b"\n")
    counts = {}
    for table in ("items", "item_snapshots", "collection_runs"):
        counts[table] = (
            connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            if table in tables else 0
        )
    if "collection_runs" in tables:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(collection_runs)")
        }
        if {"run_type", "status", "finished_at"} <= columns:
            running = connection.execute(
                "SELECT count(*) FROM collection_runs WHERE run_type='native' "
                "AND status='running' AND finished_at IS NULL"
            ).fetchone()[0]
            if running:
                raise RuntimeError("ACTIVE_NATIVE_RUN")
    return (
        digest.hexdigest(), len(tables), counts["items"],
        counts["item_snapshots"], counts["collection_runs"],
    )


def assess(source: Path) -> RehearsalResult:
    try:
        if source.is_symlink() or not source.is_file():
            return _blocked("SOURCE_INVALID")
        before_sha = _sha256(source)
        with tempfile.TemporaryDirectory(prefix="data-lab-expansion-") as directory:
            working = Path(directory) / "working.db"
            restored = Path(directory) / "restored.db"
            with closing(_read_only(source)) as source_connection:
                source_connection.execute("BEGIN")
                source_state = _state(source_connection)
                with closing(sqlite3.connect(working)) as working_connection:
                    source_connection.backup(working_connection, pages=256, sleep=0.05)
                source_connection.rollback()
            with closing(_read_only(working)) as working_connection:
                working_state = _state(working_connection)
                with closing(sqlite3.connect(restored)) as restored_connection:
                    working_connection.backup(restored_connection, pages=256, sleep=0.05)
            with closing(_read_only(restored)) as restored_connection:
                restored_state = _state(restored_connection)
            logical_match = source_state == working_state == restored_state
            if not logical_match:
                return _blocked("LOGICAL_RESTORE_MISMATCH")
        after_sha = _sha256(source)
        if before_sha != after_sha:
            return _blocked("SOURCE_IDENTITY_CHANGED")
        digest, tables, items, snapshots, runs = source_state
        return RehearsalResult(
            VERSION, VERIFIED, before_sha, tables, items, snapshots, runs,
            bool(digest) and logical_match, True, False, False, 0,
            ("DISPOSABLE_COPY_ONLY", "NO_API_OR_PRODUCTION_WRITE"),
        )
    except RuntimeError as error:
        return _blocked(str(error) if str(error) == "ACTIVE_NATIVE_RUN" else "REHEARSAL_FAILED")
    except (OSError, sqlite3.Error, ValueError):
        return _blocked("REHEARSAL_FAILED")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-db", required=True, type=Path)
    args = parser.parse_args(argv)
    result = assess(args.source_db)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == VERIFIED else 2


if __name__ == "__main__":
    raise SystemExit(main())
