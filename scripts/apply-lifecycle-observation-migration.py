"""Explicit, fail-closed migration gate for the local production SQLite DB.

The existing copy-only migration remains the only migration for arbitrary
copies. This runner needs an exact path, expected SHA-256, backup directory,
and --apply before it can write. It never restores, retries, or runs collection.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "db" / "schema.sql"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
TABLE_NAME = "item_lifecycle_observations"
ITEM_DIGEST_COLUMNS = (
    "id", "site", "service", "floor", "content_id", "product_id", "title",
    "source_date", "maker_json", "series_json", "actress_json", "genre_json",
    "image_url_large", "item_url", "first_observed_at", "last_observed_at",
    "master_updated_at",
)


def _load_backup_module():
    specification = importlib.util.spec_from_file_location(
        "lifecycle_migration_backup", ROOT / "scripts" / "backup-data-lab-db.py"
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("BACKUP_MODULE_UNAVAILABLE")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


backup = _load_backup_module()


class MigrationGateFailure(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _table_exists(connection: sqlite3.Connection) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (TABLE_NAME,)
    ).fetchone() is not None


def _create_table_sql() -> str:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    marker = "CREATE TABLE item_lifecycle_observations ("
    start = schema.find(marker)
    end = schema.find("\n) STRICT;", start)
    if start < 0 or end < 0:
        raise MigrationGateFailure("MIGRATION_SCHEMA_INVALID")
    return schema[start : end + len("\n) STRICT;")]


def _sidecars_present(path: Path) -> bool:
    return any(Path(f"{path}{suffix}").exists() for suffix in ("-wal", "-shm"))


def _validate_expected_hash(database_path: Path, expected_sha256: str) -> None:
    if not SHA256_PATTERN.fullmatch(expected_sha256):
        raise MigrationGateFailure("EXPECTED_HASH_INVALID")
    if backup.sha256_file(database_path) != expected_sha256:
        raise MigrationGateFailure("PRE_MIGRATION_HASH_MISMATCH")


def _logical_state(connection: sqlite3.Connection):
    state = backup.validate_database(
        connection, include_digests=True, validation_exit_code=1, schema_exit_code=1
    )
    items_digest = backup.logical_digest(connection, "items", ITEM_DIGEST_COLUMNS, "id")
    return state, items_digest


def preflight(database_path: Path, expected_sha256: str, backup_dir: Path) -> dict[str, int]:
    """Check all prerequisites without creating a backup or writing the DB."""
    if not database_path.is_file():
        raise MigrationGateFailure("TARGET_DATABASE_NOT_FOUND")
    if not backup_dir.is_dir():
        raise MigrationGateFailure("BACKUP_DIRECTORY_INVALID")
    if _sidecars_present(database_path):
        raise MigrationGateFailure("SQLITE_SIDECAR_PRESENT")
    _validate_expected_hash(database_path, expected_sha256)
    try:
        backup.validate_disk_space(database_path, backup_dir)
        with closing(backup.read_only_connection(database_path)) as connection:
            state, _ = _logical_state(connection)
            if state.native_running:
                raise MigrationGateFailure("ACTIVE_NATIVE_RUN")
            if _table_exists(connection):
                raise MigrationGateFailure("TARGET_TABLE_ALREADY_EXISTS")
    except MigrationGateFailure:
        raise
    except (backup.BackupFailure, OSError, sqlite3.Error):
        raise MigrationGateFailure("DATABASE_PREFLIGHT_FAILED") from None
    return {"items": state.items, "snapshots": state.snapshots,
            "collection_runs": state.collection_runs, "lifecycle_observations": 0}


def _create_schema_objects(connection: sqlite3.Connection) -> None:
    connection.execute(_create_table_sql())
    connection.execute(
        "CREATE INDEX idx_item_lifecycle_observations_observed_at "
        "ON item_lifecycle_observations (observed_at DESC)"
    )


def apply(database_path: Path, expected_sha256: str, backup_dir: Path) -> dict[str, int]:
    """Create a verified backup then atomically add the empty schema objects."""
    preflight(database_path, expected_sha256, backup_dir)
    final_name, temporary_name = backup.planned_names()
    try:
        backup_path, source_state, backup_state, _ = backup.perform_backup(
            database_path, backup_dir, final_name, temporary_name
        )
        if not backup.states_match(source_state, backup_state) or not backup.sha256_file(backup_path):
            raise MigrationGateFailure("BACKUP_VERIFICATION_FAILED")
    except MigrationGateFailure:
        raise
    except (backup.BackupFailure, OSError, sqlite3.Error):
        raise MigrationGateFailure("BACKUP_CREATION_FAILED") from None
    if _sidecars_present(database_path):
        raise MigrationGateFailure("SQLITE_SIDECAR_PRESENT")
    _validate_expected_hash(database_path, expected_sha256)
    connection = sqlite3.connect(database_path, isolation_level=None)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        try:
            if _table_exists(connection):
                raise MigrationGateFailure("TARGET_TABLE_ALREADY_EXISTS")
            before_state, before_items_digest = _logical_state(connection)
            if before_state.native_running:
                raise MigrationGateFailure("ACTIVE_NATIVE_RUN")
            _create_schema_objects(connection)
            after_state, after_items_digest = _logical_state(connection)
            if (before_state.items != after_state.items or
                    before_state.snapshots != after_state.snapshots or
                    before_state.collection_runs != after_state.collection_runs or
                    before_items_digest != after_items_digest or
                    before_state.snapshot_digest != after_state.snapshot_digest or
                    before_state.collection_run_digest != after_state.collection_run_digest):
                raise MigrationGateFailure("EXISTING_DATA_CHANGED")
            if connection.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0] != 0:
                raise MigrationGateFailure("AUTOMATIC_BACKFILL_FORBIDDEN")
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise MigrationGateFailure("FOREIGN_KEY_CHECK_FAILED")
            if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise MigrationGateFailure("INTEGRITY_CHECK_FAILED")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    except MigrationGateFailure:
        raise
    except (backup.BackupFailure, OSError, sqlite3.Error):
        raise MigrationGateFailure("MIGRATION_DATABASE_OPERATION_FAILED") from None
    finally:
        connection.close()
    return {"items": before_state.items, "snapshots": before_state.snapshots,
            "collection_runs": before_state.collection_runs, "lifecycle_observations": 0}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the explicit lifecycle migration gate.")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--backup-dir", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    database_path, backup_dir = args.db.expanduser().resolve(), args.backup_dir.expanduser().resolve()
    try:
        result = apply(database_path, args.expected_sha256, backup_dir) if args.apply else preflight(database_path, args.expected_sha256, backup_dir)
    except MigrationGateFailure as error:
        print("migration_status: blocked", file=sys.stderr)
        print(f"error_code: {error.code}", file=sys.stderr)
        return 1
    print(f"migration_status: {'applied' if args.apply else 'ready'}")
    print(f"apply: {'true' if args.apply else 'false'}")
    for key in sorted(result):
        print(f"{key}: {result[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
