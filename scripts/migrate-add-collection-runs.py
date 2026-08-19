from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


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
RECOVERABLE_FIELDS = ("site", "service", "floor", "source_sort", "hits")


class MigrationFailure(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def fail(code: str) -> None:
    raise MigrationFailure(code)


def extract_create_table(schema: str, table_name: str) -> str:
    marker = f"CREATE TABLE {table_name} ("
    start = schema.find(marker)
    if start < 0:
        fail("SCHEMA_DEFINITION_MISSING")
    end_marker = "\n) STRICT;"
    end = schema.find(end_marker, start)
    if end < 0:
        fail("SCHEMA_DEFINITION_INVALID")
    return schema[start : end + len(end_marker)]


def table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }


def scalar(connection: sqlite3.Connection, sql: str) -> int:
    row = connection.execute(sql).fetchone()
    if row is None:
        fail("VALIDATION_QUERY_FAILED")
    return int(row[0])


def snapshot_digest(connection: sqlite3.Connection) -> str:
    digest = hashlib.sha256()
    column_sql = ", ".join(SNAPSHOT_COLUMNS)
    for row in connection.execute(
        f"SELECT {column_sql} FROM item_snapshots ORDER BY id"
    ):
        encoded = json.dumps(
            list(row), ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def valid_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def valid_positive_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def recover_legacy_run(
    rows: list[sqlite3.Row],
) -> tuple[dict[str, Any], set[str]]:
    values: dict[str, list[Any]] = {
        field: [] for field in RECOVERABLE_FIELDS
    }
    invalid: set[str] = set()

    for row in rows:
        try:
            context = json.loads(row["query_context_json"])
        except (TypeError, ValueError):
            context = None

        if not isinstance(context, dict):
            invalid.update(RECOVERABLE_FIELDS)
            continue

        for field in ("site", "service", "floor"):
            value = context.get(field)
            if valid_nonempty_string(value):
                values[field].append(value)
            else:
                invalid.add(field)

        hits = context.get("hits")
        if valid_positive_integer(hits):
            values["hits"].append(hits)
        else:
            invalid.add("hits")

        context_sort = context.get("sort")
        snapshot_sort = row["source_sort"]
        if (
            valid_nonempty_string(context_sort)
            and valid_nonempty_string(snapshot_sort)
            and context_sort == snapshot_sort
        ):
            values["source_sort"].append(context_sort)
        else:
            invalid.add("source_sort")

    recovered: dict[str, Any] = {}
    for field in RECOVERABLE_FIELDS:
        distinct_values = set(values[field])
        if field in invalid or len(values[field]) != len(rows) or len(distinct_values) != 1:
            recovered[field] = None
            invalid.add(field)
        else:
            recovered[field] = next(iter(distinct_values))

    return recovered, invalid


def validate_before(connection: sqlite3.Connection) -> dict[str, int | str]:
    tables = table_names(connection)
    if not {"items", "item_snapshots"}.issubset(tables):
        fail("REQUIRED_TABLE_MISSING")
    if "collection_runs" in tables:
        fail("ALREADY_MIGRATED")
    if scalar(connection, "PRAGMA foreign_keys") != 1:
        fail("FOREIGN_KEYS_NOT_ENABLED")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        fail("PREEXISTING_FOREIGN_KEY_VIOLATION")
    if scalar(
        connection,
        "SELECT COUNT(*) FROM item_snapshots WHERE collection_run_id IS NULL",
    ):
        fail("NULL_COLLECTION_RUN_ID")
    if scalar(
        connection,
        """
        SELECT COUNT(*) FROM item_snapshots AS s
        LEFT JOIN items AS i ON i.id = s.item_id
        WHERE i.id IS NULL
        """,
    ):
        fail("ORPHAN_ITEM_ID")
    if scalar(
        connection,
        "SELECT COUNT(*) FROM item_snapshots WHERE NOT json_valid(query_context_json)",
    ):
        fail("INVALID_QUERY_CONTEXT_JSON")
    duplicate_groups = scalar(
        connection,
        """
        SELECT COUNT(*) FROM (
          SELECT 1
          FROM item_snapshots
          GROUP BY collection_run_id, source_offset, source_position
          HAVING COUNT(*) > 1
        )
        """,
    )
    if duplicate_groups:
        fail("SNAPSHOT_UNIQUE_DUPLICATE")

    items_count = scalar(connection, "SELECT COUNT(*) FROM items")
    snapshots_count = scalar(connection, "SELECT COUNT(*) FROM item_snapshots")
    runs_count = scalar(
        connection,
        "SELECT COUNT(DISTINCT collection_run_id) FROM item_snapshots",
    )
    return {
        "items": items_count,
        "snapshots": snapshots_count,
        "runs": runs_count,
        "snapshot_digest": snapshot_digest(connection),
    }


def validate_snapshot_copy(connection: sqlite3.Connection) -> None:
    columns = ", ".join(SNAPSHOT_COLUMNS)
    difference_count = scalar(
        connection,
        f"""
        SELECT COUNT(*) FROM (
          SELECT {columns} FROM item_snapshots
          EXCEPT
          SELECT {columns} FROM item_snapshots_new
        )
        """,
    ) + scalar(
        connection,
        f"""
        SELECT COUNT(*) FROM (
          SELECT {columns} FROM item_snapshots_new
          EXCEPT
          SELECT {columns} FROM item_snapshots
        )
        """,
    )
    if difference_count:
        fail("SNAPSHOT_CONTENT_MISMATCH")


def validate_after(
    connection: sqlite3.Connection,
    before: dict[str, int | str],
) -> dict[str, int | str]:
    items_count = scalar(connection, "SELECT COUNT(*) FROM items")
    snapshots_count = scalar(connection, "SELECT COUNT(*) FROM item_snapshots")
    runs_count = scalar(connection, "SELECT COUNT(*) FROM collection_runs")
    distinct_runs = scalar(
        connection,
        "SELECT COUNT(DISTINCT collection_run_id) FROM item_snapshots",
    )
    if items_count != before["items"]:
        fail("ITEM_COUNT_MISMATCH")
    if snapshots_count != before["snapshots"]:
        fail("SNAPSHOT_COUNT_MISMATCH")
    if runs_count != before["runs"] or distinct_runs != runs_count:
        fail("RUN_COUNT_MISMATCH")
    if scalar(
        connection,
        """
        SELECT COUNT(*) FROM item_snapshots AS s
        LEFT JOIN collection_runs AS r
          ON r.collection_run_id = s.collection_run_id
        WHERE r.collection_run_id IS NULL
        """,
    ):
        fail("ORPHAN_COLLECTION_RUN_ID")
    if scalar(
        connection,
        """
        SELECT COUNT(*) FROM item_snapshots AS s
        LEFT JOIN items AS i ON i.id = s.item_id
        WHERE i.id IS NULL
        """,
    ):
        fail("ORPHAN_ITEM_ID_AFTER")
    if scalar(
        connection,
        "SELECT COUNT(*) FROM item_snapshots WHERE NOT json_valid(query_context_json)",
    ):
        fail("INVALID_JSON_AFTER")
    if scalar(
        connection,
        """
        SELECT COUNT(*) FROM collection_runs AS r
        WHERE r.run_type != 'legacy_migrated'
           OR r.status != 'unknown'
           OR r.collection_complete IS NOT NULL
           OR r.stop_reason IS NOT NULL
           OR r.error_code IS NOT NULL
           OR r.started_at IS NOT NULL
           OR r.finished_at IS NOT NULL
           OR r.max_items IS NOT NULL
           OR r.max_pages IS NOT NULL
           OR r.snapshots_inserted != (
             SELECT COUNT(*) FROM item_snapshots AS s
             WHERE s.collection_run_id = r.collection_run_id
           )
           OR r.first_observed_at IS NOT (
             SELECT MIN(s.observed_at) FROM item_snapshots AS s
             WHERE s.collection_run_id = r.collection_run_id
           )
           OR r.last_observed_at IS NOT (
             SELECT MAX(s.observed_at) FROM item_snapshots AS s
             WHERE s.collection_run_id = r.collection_run_id
           )
        """,
    ):
        fail("LEGACY_RUN_VALIDATION_FAILED")
    foreign_key_violations = len(
        connection.execute("PRAGMA foreign_key_check").fetchall()
    )
    if foreign_key_violations:
        fail("FOREIGN_KEY_CHECK_FAILED")
    integrity_row = connection.execute("PRAGMA integrity_check").fetchone()
    integrity_result = str(integrity_row[0]) if integrity_row else "unavailable"
    if integrity_result != "ok":
        fail("INTEGRITY_CHECK_FAILED")
    digest = snapshot_digest(connection)
    if digest != before["snapshot_digest"]:
        fail("SNAPSHOT_DIGEST_MISMATCH")
    return {
        "items": items_count,
        "snapshots": snapshots_count,
        "runs": runs_count,
        "foreign_key_violations": foreign_key_violations,
        "integrity": integrity_result,
        "snapshot_content_match": "true",
    }


def migrate(database_path: Path) -> tuple[dict[str, int | str], dict[str, int], dict[str, int | str]]:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    create_runs = extract_create_table(schema, "collection_runs")
    create_snapshots = extract_create_table(schema, "item_snapshots").replace(
        "CREATE TABLE item_snapshots (",
        "CREATE TABLE item_snapshots_new (",
        1,
    )
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        before = validate_before(connection)
        recovery_failures = {field: 0 for field in RECOVERABLE_FIELDS}

        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(create_runs)
            run_ids = [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT collection_run_id FROM item_snapshots ORDER BY collection_run_id"
                )
            ]
            for run_id in run_ids:
                rows = connection.execute(
                    """
                    SELECT observed_at, source_sort, query_context_json
                    FROM item_snapshots
                    WHERE collection_run_id = ?
                    ORDER BY id
                    """,
                    (run_id,),
                ).fetchall()
                recovered, invalid = recover_legacy_run(rows)
                for field in invalid:
                    recovery_failures[field] += 1
                observed_values = [row["observed_at"] for row in rows]
                connection.execute(
                    """
                    INSERT INTO collection_runs (
                      collection_run_id, run_type, first_observed_at,
                      last_observed_at, site, service, floor, source_sort,
                      hits, snapshots_inserted, status
                    ) VALUES (?, 'legacy_migrated', ?, ?, ?, ?, ?, ?, ?, ?, 'unknown')
                    """,
                    (
                        run_id,
                        min(observed_values),
                        max(observed_values),
                        recovered["site"],
                        recovered["service"],
                        recovered["floor"],
                        recovered["source_sort"],
                        recovered["hits"],
                        len(rows),
                    ),
                )

            connection.execute(create_snapshots)
            columns = ", ".join(SNAPSHOT_COLUMNS)
            connection.execute(
                f"INSERT INTO item_snapshots_new ({columns}) SELECT {columns} FROM item_snapshots"
            )
            validate_snapshot_copy(connection)
            if scalar(connection, "SELECT COUNT(*) FROM item_snapshots_new") != before["snapshots"]:
                fail("SNAPSHOT_COPY_COUNT_MISMATCH")

            connection.execute("DROP TABLE item_snapshots")
            connection.execute("ALTER TABLE item_snapshots_new RENAME TO item_snapshots")
            connection.execute(
                """
                CREATE INDEX idx_item_snapshots_observed_at
                  ON item_snapshots (observed_at DESC)
                """
            )
            after = validate_after(connection, before)
            connection.commit()
        except Exception:
            connection.rollback()
            raise

        # Recheck the committed state, including a complete row-content digest.
        committed = validate_after(connection, before)
        if committed != after:
            fail("POST_COMMIT_VALIDATION_MISMATCH")
        return before, recovery_failures, committed
    finally:
        connection.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate an explicitly selected SQLite copy to collection_runs."
    )
    parser.add_argument("--db", required=True, type=Path, help="Path to a copied DB")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
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

    print("migration: started")
    try:
        before, recovery_failures, after = migrate(database_path)
    except MigrationFailure as error:
        print(f"migration failed: {error.code}", file=sys.stderr)
        return 1
    except (OSError, sqlite3.Error):
        print("migration failed: DATABASE_OPERATION_FAILED", file=sys.stderr)
        return 1
    except Exception:
        print("migration failed: UNEXPECTED_ERROR", file=sys.stderr)
        return 1

    print("migration: success")
    print(f"items_before: {before['items']}")
    print(f"items_after: {after['items']}")
    print(f"snapshots_before: {before['snapshots']}")
    print(f"snapshots_after: {after['snapshots']}")
    print(f"legacy_runs: {after['runs']}")
    for field in RECOVERABLE_FIELDS:
        print(f"unrecovered_{field}_runs: {recovery_failures[field]}")
    print(f"foreign_key_check_violations: {after['foreign_key_violations']}")
    print(f"integrity_check: {after['integrity']}")
    print(f"snapshot_content_match: {after['snapshot_content_match']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("migration failed: UNEXPECTED_ERROR", file=sys.stderr)
        raise SystemExit(1)
