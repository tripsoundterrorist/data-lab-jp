"""Add the sanitized lifecycle observation table to an explicit DB copy.

This migration never targets the repository's configured database and never
backfills evidence. Existing item and snapshot rows are left unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "db" / "schema.sql"
PRODUCTION_DATABASE_PATH = (ROOT / "data" / "data-lab.db").resolve()
SNAPSHOT_COLUMNS = (
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


class MigrationFailure(Exception):
    pass


def _create_table_sql(schema: str) -> str:
    marker = "CREATE TABLE item_lifecycle_observations ("
    start = schema.find(marker)
    end_marker = "\n) STRICT;"
    end = schema.find(end_marker, start)
    if start < 0 or end < 0:
        raise MigrationFailure("SCHEMA_DEFINITION_INVALID")
    return schema[start : end + len(end_marker)]


def _snapshot_digest(connection: sqlite3.Connection) -> str:
    digest = hashlib.sha256()
    columns = ", ".join(SNAPSHOT_COLUMNS)
    for row in connection.execute(
        f"SELECT {columns} FROM item_snapshots ORDER BY id"
    ):
        encoded = json.dumps(
            list(row), ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def migrate(database_path: Path) -> dict[str, int | str]:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    create_table = _create_table_sql(schema)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        existing = connection.execute(
            """
            SELECT COUNT(*) FROM sqlite_master
            WHERE type = 'table' AND name = 'item_lifecycle_observations'
            """
        ).fetchone()[0]
        if existing:
            raise MigrationFailure("TARGET_TABLE_ALREADY_EXISTS")
        before_count = connection.execute(
            "SELECT COUNT(*) FROM item_snapshots"
        ).fetchone()[0]
        before_digest = _snapshot_digest(connection)

        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(create_table)
            connection.execute(
                """
                CREATE INDEX idx_item_lifecycle_observations_observed_at
                  ON item_lifecycle_observations (observed_at DESC)
                """
            )
            if connection.execute(
                "SELECT COUNT(*) FROM item_lifecycle_observations"
            ).fetchone()[0] != 0:
                raise MigrationFailure("AUTOMATIC_BACKFILL_FORBIDDEN")
            if connection.execute(
                "SELECT COUNT(*) FROM item_snapshots"
            ).fetchone()[0] != before_count:
                raise MigrationFailure("SNAPSHOT_COUNT_CHANGED")
            if _snapshot_digest(connection) != before_digest:
                raise MigrationFailure("SNAPSHOT_CONTENT_CHANGED")
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise MigrationFailure("FOREIGN_KEY_CHECK_FAILED")
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                raise MigrationFailure("INTEGRITY_CHECK_FAILED")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        return {
            "snapshots_preserved": before_count,
            "lifecycle_observations_created": 0,
            "integrity": "ok",
        }
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Add sanitized lifecycle observations to a copied DB."
    )
    parser.add_argument("--db", required=True, type=Path)
    args = parser.parse_args(argv)
    database_path = args.db.expanduser().resolve()
    same_as_production = database_path == PRODUCTION_DATABASE_PATH
    if database_path.exists() and PRODUCTION_DATABASE_PATH.exists():
        try:
            same_as_production = same_as_production or database_path.samefile(
                PRODUCTION_DATABASE_PATH
            )
        except OSError:
            print("migration failed: TARGET_IDENTITY_CHECK_FAILED", file=sys.stderr)
            return 1
    if same_as_production:
        print("migration failed: PRODUCTION_DATABASE_REFUSED", file=sys.stderr)
        return 1
    if not database_path.is_file():
        print("migration failed: TARGET_DATABASE_NOT_FOUND", file=sys.stderr)
        return 1
    try:
        result = migrate(database_path)
    except MigrationFailure as error:
        print(f"migration failed: {error}", file=sys.stderr)
        return 1
    except (OSError, sqlite3.Error):
        print("migration failed: DATABASE_OPERATION_FAILED", file=sys.stderr)
        return 1
    print("migration: success")
    for key in sorted(result):
        print(f"{key}: {result[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
