from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE_DB = ROOT / "data" / "data-lab.db"
DEFAULT_BACKUP_DIR = ROOT / "data" / "backups" / "daily"
MIN_FREE_BYTES = 256 * 1024 * 1024
SOURCE_SIZE_MULTIPLIER = 3
BACKUP_RETENTION_COUNT = 7
LOCK_TIMEOUT_SECONDS = 5

REQUIRED_COLUMNS = {
    "items": {
        "id",
        "site",
        "service",
        "floor",
        "content_id",
    },
    "item_snapshots": {
        "id",
        "item_id",
        "collection_run_id",
        "observed_at",
        "source_sort",
        "source_offset",
        "source_position",
        "price_raw",
        "price_min",
        "review_average",
        "review_count",
        "query_context_json",
    },
    "collection_runs": {
        "collection_run_id",
        "run_type",
        "started_at",
        "finished_at",
        "status",
        "collection_complete",
    },
}

SNAPSHOT_DIGEST_COLUMNS = (
    "id",
    "item_id",
    "collection_run_id",
    "observed_at",
    "source_sort",
    "source_offset",
    "source_position",
    "price_raw",
    "price_min",
    "review_average",
    "review_count",
    "query_context_json",
)

COLLECTION_RUN_DIGEST_COLUMNS = (
    "collection_run_id",
    "run_type",
    "started_at",
    "finished_at",
    "first_observed_at",
    "last_observed_at",
    "site",
    "service",
    "floor",
    "source_sort",
    "hits",
    "max_items",
    "max_pages",
    "api_calls",
    "pages_fetched",
    "api_total_count_initial",
    "total_count_changed",
    "fetched_items",
    "processed_items",
    "duplicate_content_ids_across_pages",
    "items_upserted",
    "snapshots_inserted",
    "collection_complete",
    "status",
    "stop_reason",
    "error_code",
)


class BackupFailure(Exception):
    def __init__(self, exit_code: int, error_code: str) -> None:
        super().__init__(error_code)
        self.exit_code = exit_code
        self.error_code = error_code


@dataclass(frozen=True)
class DatabaseState:
    items: int
    snapshots: int
    collection_runs: int
    native_running: int
    snapshot_digest: str | None = None
    collection_run_digest: str | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def read_only_connection(path: Path) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def validate_schema(connection: sqlite3.Connection, exit_code: int) -> None:
    tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type = 'table'"
        )
    }
    if not REQUIRED_COLUMNS.keys() <= tables:
        raise BackupFailure(exit_code, "DATABASE_SCHEMA_MISMATCH")
    for table, required in REQUIRED_COLUMNS.items():
        if not required <= table_columns(connection, table):
            raise BackupFailure(exit_code, "DATABASE_SCHEMA_MISMATCH")


def scalar(connection: sqlite3.Connection, sql: str) -> int:
    row = connection.execute(sql).fetchone()
    if row is None:
        raise BackupFailure(1, "INTERNAL_QUERY_FAILURE")
    return int(row[0])


def logical_digest(
    connection: sqlite3.Connection,
    table: str,
    columns: Iterable[str],
    order_by: str,
) -> str:
    column_sql = ", ".join(columns)
    digest = hashlib.sha256()
    for row in connection.execute(
        f"SELECT {column_sql} FROM {table} ORDER BY {order_by}"
    ):
        encoded = json.dumps(
            list(row), ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def validate_database(
    connection: sqlite3.Connection,
    *,
    include_digests: bool,
    validation_exit_code: int,
    schema_exit_code: int,
) -> DatabaseState:
    validate_schema(connection, schema_exit_code)

    integrity_rows = [str(row[0]) for row in connection.execute("PRAGMA integrity_check")]
    if integrity_rows != ["ok"]:
        raise BackupFailure(validation_exit_code, "DATABASE_INTEGRITY_FAILURE")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise BackupFailure(validation_exit_code, "DATABASE_FOREIGN_KEY_FAILURE")

    orphan_items = scalar(
        connection,
        """
        SELECT COUNT(*) FROM item_snapshots AS s
        LEFT JOIN items AS i ON i.id = s.item_id
        WHERE i.id IS NULL
        """,
    )
    orphan_runs = scalar(
        connection,
        """
        SELECT COUNT(*) FROM item_snapshots AS s
        LEFT JOIN collection_runs AS r
          ON r.collection_run_id = s.collection_run_id
        WHERE r.collection_run_id IS NULL
        """,
    )
    duplicate_groups = scalar(
        connection,
        """
        SELECT COUNT(*) FROM (
          SELECT collection_run_id, source_offset, source_position
          FROM item_snapshots
          GROUP BY collection_run_id, source_offset, source_position
          HAVING COUNT(*) > 1
        )
        """,
    )
    if orphan_items or orphan_runs or duplicate_groups:
        raise BackupFailure(validation_exit_code, "DATABASE_RELATIONSHIP_FAILURE")

    state = DatabaseState(
        items=scalar(connection, "SELECT COUNT(*) FROM items"),
        snapshots=scalar(connection, "SELECT COUNT(*) FROM item_snapshots"),
        collection_runs=scalar(connection, "SELECT COUNT(*) FROM collection_runs"),
        native_running=scalar(
            connection,
            """
            SELECT COUNT(*) FROM collection_runs
            WHERE run_type = 'native'
              AND status = 'running'
              AND finished_at IS NULL
            """,
        ),
        snapshot_digest=(
            logical_digest(
                connection,
                "item_snapshots",
                SNAPSHOT_DIGEST_COLUMNS,
                "id",
            )
            if include_digests
            else None
        ),
        collection_run_digest=(
            logical_digest(
                connection,
                "collection_runs",
                COLLECTION_RUN_DIGEST_COLUMNS,
                "collection_run_id",
            )
            if include_digests
            else None
        ),
    )
    return state


def nearest_existing_directory(path: Path) -> Path:
    candidate = path.resolve()
    while not candidate.exists():
        parent = candidate.parent
        if parent == candidate:
            raise BackupFailure(5, "BACKUP_DIRECTORY_UNAVAILABLE")
        candidate = parent
    if not candidate.is_dir():
        raise BackupFailure(5, "BACKUP_DIRECTORY_UNAVAILABLE")
    return candidate


def validate_disk_space(source_db: Path, backup_dir: Path) -> tuple[int, int]:
    try:
        probe = nearest_existing_directory(backup_dir)
        if not os.access(probe, os.W_OK):
            raise BackupFailure(5, "BACKUP_DIRECTORY_UNAVAILABLE")
        free_bytes = shutil.disk_usage(probe).free
        required_bytes = max(MIN_FREE_BYTES, source_db.stat().st_size * SOURCE_SIZE_MULTIPLIER)
    except (OSError, BackupFailure) as error:
        if isinstance(error, BackupFailure):
            raise
        raise BackupFailure(5, "DISK_SPACE_UNAVAILABLE") from None
    if free_bytes < required_bytes:
        raise BackupFailure(5, "DISK_SPACE_INSUFFICIENT")
    return free_bytes, required_bytes


def existing_backup_files(backup_dir: Path) -> list[Path]:
    if not backup_dir.exists():
        return []
    return [path for path in backup_dir.glob("data-lab-*.db") if path.is_file()]


def rotate_backups(backup_dir: Path) -> bool:
    warning = False
    try:
        candidates = sorted(
            existing_backup_files(backup_dir),
            key=lambda path: (path.stat().st_mtime_ns, path.name),
            reverse=True,
        )
    except OSError:
        return True
    for old_backup in candidates[BACKUP_RETENTION_COUNT:]:
        try:
            old_backup.unlink()
        except OSError:
            warning = True
    return warning


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def states_match(source: DatabaseState, backup: DatabaseState) -> bool:
    return (
        source.items == backup.items
        and source.snapshots == backup.snapshots
        and source.collection_runs == backup.collection_runs
        and source.snapshot_digest == backup.snapshot_digest
        and source.collection_run_digest == backup.collection_run_digest
    )


def planned_names() -> tuple[str, str]:
    identifier = uuid.uuid4().hex
    timestamp = utc_timestamp()
    final_name = f"data-lab-{timestamp}-{identifier[:12]}.db"
    temporary_name = f".tmp-data-lab-{timestamp}-{identifier}.db"
    return final_name, temporary_name


def perform_backup(source_db: Path, backup_dir: Path, final_name: str, temporary_name: str) -> tuple[Path, DatabaseState, DatabaseState, bool]:
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise BackupFailure(6, "BACKUP_DIRECTORY_CREATE_FAILURE") from None

    temporary_path = backup_dir / temporary_name
    final_path = backup_dir / final_name
    lock_connection: sqlite3.Connection | None = None
    source_connection: sqlite3.Connection | None = None
    destination_connection: sqlite3.Connection | None = None

    try:
        lock_connection = sqlite3.connect(
            source_db,
            timeout=LOCK_TIMEOUT_SECONDS,
            isolation_level=None,
        )
        lock_connection.execute("PRAGMA foreign_keys = ON")
        try:
            lock_connection.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError:
            raise BackupFailure(2, "SOURCE_DATABASE_BUSY") from None
        running = scalar(
            lock_connection,
            """
            SELECT COUNT(*) FROM collection_runs
            WHERE run_type = 'native'
              AND status = 'running'
              AND finished_at IS NULL
            """,
        )
        if running:
            raise BackupFailure(2, "ACTIVE_NATIVE_RUN")

        source_connection = read_only_connection(source_db)
        source_connection.execute("BEGIN")
        source_state = validate_database(
            source_connection,
            include_digests=True,
            validation_exit_code=3,
            schema_exit_code=4,
        )

        destination_connection = sqlite3.connect(temporary_path)
        source_connection.backup(destination_connection, pages=256, sleep=0.05)
        destination_connection.close()
        destination_connection = None
        source_connection.rollback()
        source_connection.close()
        source_connection = None
        lock_connection.rollback()
        lock_connection.close()
        lock_connection = None

        with closing(read_only_connection(temporary_path)) as backup_connection:
            backup_state = validate_database(
                backup_connection,
                include_digests=True,
                validation_exit_code=7,
                schema_exit_code=7,
            )
        if not states_match(source_state, backup_state):
            raise BackupFailure(7, "BACKUP_LOGICAL_MISMATCH")

        temporary_path.rename(final_path)
        rotation_warning = rotate_backups(backup_dir)
        return final_path, source_state, backup_state, rotation_warning
    except BackupFailure:
        raise
    except sqlite3.OperationalError:
        raise BackupFailure(6, "BACKUP_DATABASE_OPERATION_FAILURE") from None
    except (OSError, sqlite3.Error):
        raise BackupFailure(6, "BACKUP_CREATION_FAILURE") from None
    finally:
        if destination_connection is not None:
            destination_connection.close()
        if source_connection is not None:
            try:
                source_connection.rollback()
            except sqlite3.Error:
                pass
            source_connection.close()
        if lock_connection is not None:
            try:
                lock_connection.rollback()
            except sqlite3.Error:
                pass
            lock_connection.close()
        if temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create and validate a DATA LAB SQLite backup.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source-db", type=Path, default=DEFAULT_SOURCE_DB)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source_db = args.source_db.resolve()
    backup_dir = args.backup_dir.resolve()
    final_name, temporary_name = planned_names()

    try:
        if not source_db.is_file():
            raise BackupFailure(4, "SOURCE_DATABASE_MISSING")
        free_bytes, required_bytes = validate_disk_space(source_db, backup_dir)
        with closing(read_only_connection(source_db)) as connection:
            source_state = validate_database(
                connection,
                include_digests=False,
                validation_exit_code=3,
                schema_exit_code=4,
            )
        if source_state.native_running:
            raise BackupFailure(2, "ACTIVE_NATIVE_RUN")

        if args.dry_run:
            print("backup_status: ready")
            print("dry_run: true")
            print(f"items: {source_state.items}")
            print(f"item_snapshots: {source_state.snapshots}")
            print(f"collection_runs: {source_state.collection_runs}")
            print(f"native_running: {source_state.native_running}")
            print(f"free_space_mib: {free_bytes // (1024 * 1024)}")
            print(f"required_space_mib: {required_bytes // (1024 * 1024)}")
            print(f"daily_backup_count: {len(existing_backup_files(backup_dir))}")
            print(f"planned_backup_file: {final_name}")
            print("backup_created: false")
            return 0

        final_path, locked_source, backup_state, rotation_warning = perform_backup(
            source_db,
            backup_dir,
            final_name,
            temporary_name,
        )
        print("backup_status: success")
        print(f"backup_file: {final_path.name}")
        print(f"items: {backup_state.items}")
        print(f"item_snapshots: {backup_state.snapshots}")
        print(f"collection_runs: {backup_state.collection_runs}")
        print("snapshot_digest_match: true")
        print("collection_run_digest_match: true")
        print(f"backup_sha256: {sha256_file(final_path)}")
        try:
            retained_count: int | str = len(existing_backup_files(backup_dir))
        except OSError:
            retained_count = "unknown"
            rotation_warning = True
        print(f"retained_backups: {retained_count}")
        if rotation_warning:
            print("warning: BACKUP_ROTATION_FAILED")
        return 0
    except BackupFailure as error:
        print("backup_status: failed", file=sys.stderr)
        print(f"error_code: {error.error_code}", file=sys.stderr)
        return error.exit_code
    except Exception:
        print("backup_status: failed", file=sys.stderr)
        print("error_code: UNEXPECTED_ERROR", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
