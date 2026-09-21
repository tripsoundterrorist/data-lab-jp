"""Add empty immutable snapshot-title provenance to an explicit DB copy."""
from __future__ import annotations
import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "db" / "schema.sql"

class MigrationFailure(Exception): pass

def _sql() -> str:
    text = SCHEMA.read_text(encoding="utf-8"); marker = "CREATE TABLE item_snapshot_titles ("
    start = text.find(marker); end = text.find("\n) STRICT;", start)
    if start < 0 or end < 0: raise MigrationFailure("SCHEMA_DEFINITION_INVALID")
    return text[start:end + len("\n) STRICT;")]

def migrate(path: Path) -> dict[str, int]:
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        required = {"items", "item_snapshots", "collection_runs", "item_lifecycle_observations"}
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not required <= tables: raise MigrationFailure("REQUIRED_SCHEMA_MISSING")
        if "item_snapshot_titles" in tables: raise MigrationFailure("TARGET_TABLE_ALREADY_EXISTS")
        before = tuple(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("items", "item_snapshots", "collection_runs", "item_lifecycle_observations"))
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(_sql())
            if connection.execute("SELECT COUNT(*) FROM item_snapshot_titles").fetchone()[0] != 0: raise MigrationFailure("AUTOMATIC_BACKFILL_FORBIDDEN")
            after = tuple(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("items", "item_snapshots", "collection_runs", "item_lifecycle_observations"))
            if after != before or connection.execute("PRAGMA foreign_key_check").fetchone() is not None or connection.execute("PRAGMA integrity_check").fetchone() != ("ok",): raise MigrationFailure("EXISTING_DATA_CHANGED")
            connection.commit()
        except Exception:
            connection.rollback(); raise
        return {"snapshot_titles_created": 0}
    finally: connection.close()

def main(argv=None):
    parser=argparse.ArgumentParser(); parser.add_argument("--db", required=True, type=Path); args=parser.parse_args(argv)
    try: migrate(args.db.resolve())
    except (MigrationFailure, OSError, sqlite3.Error): print("migration failed: FAIL_CLOSED", file=sys.stderr); return 1
    print("migration: success"); print("snapshot_titles_created: 0"); return 0
if __name__ == "__main__": raise SystemExit(main())
