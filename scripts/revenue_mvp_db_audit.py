"""Read-only database baseline audit for the DATA LAB Revenue MVP."""

from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = ROOT / "data" / "data-lab.db"
AUDIT_VERSION = "0.1"
READY = "READY"
BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class DatabaseAudit:
    audit_version: str
    status: str
    database_present: bool
    database_size_bytes: int | None
    items_count: int | None
    item_snapshots_count: int | None
    collection_runs_count: int | None
    oldest_observed_at: str | None
    latest_observed_at: str | None
    average_observations_per_item: float | None
    integrity_check: str
    foreign_key_violation_count: int | None
    read_only: bool
    publication_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(**changes: Any) -> DatabaseAudit:
    values = {
        "audit_version": AUDIT_VERSION,
        "status": BLOCKED,
        "database_present": False,
        "database_size_bytes": None,
        "items_count": None,
        "item_snapshots_count": None,
        "collection_runs_count": None,
        "oldest_observed_at": None,
        "latest_observed_at": None,
        "average_observations_per_item": None,
        "integrity_check": "unavailable",
        "foreign_key_violation_count": None,
        "read_only": True,
        "publication_allowed": False,
        "reason_codes": ("DATABASE_MISSING",),
    }
    values.update(changes)
    return DatabaseAudit(**values)


def _count(connection: sqlite3.Connection, table: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    if row is None or type(row[0]) is not int:
        raise sqlite3.DatabaseError("count unavailable")
    return row[0]


def audit_database(database_path: Path) -> DatabaseAudit:
    """Return bounded aggregate facts without modifying or identifying the DB."""

    try:
        path = database_path.resolve(strict=True)
    except (OSError, RuntimeError):
        return _result()
    if not path.is_file():
        return _result()

    try:
        size = path.stat().st_size
        connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
        with closing(connection):
            connection.execute("PRAGMA query_only = ON")
            connection.execute("PRAGMA foreign_keys = ON")
            query_only = connection.execute("PRAGMA query_only").fetchone()
            if query_only != (1,):
                return _result(
                    database_present=True,
                    database_size_bytes=size,
                    read_only=False,
                    reason_codes=("READ_ONLY_ENFORCEMENT_FAILED",),
                )

            required_tables = {"items", "item_snapshots", "collection_runs"}
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            if not required_tables <= tables:
                return _result(
                    database_present=True,
                    database_size_bytes=size,
                    reason_codes=("REQUIRED_SCHEMA_MISSING",),
                )

            items = _count(connection, "items")
            snapshots = _count(connection, "item_snapshots")
            runs = _count(connection, "collection_runs")
            observed = connection.execute(
                "SELECT MIN(observed_at), MAX(observed_at) FROM item_snapshots"
            ).fetchone()
            oldest = observed[0] if observed else None
            latest = observed[1] if observed else None
            average = round(snapshots / items, 6) if items else None
            integrity_rows = [
                str(row[0])
                for row in connection.execute("PRAGMA integrity_check")
            ]
            integrity = "ok" if integrity_rows == ["ok"] else "failed"
            foreign_keys = len(
                connection.execute("PRAGMA foreign_key_check").fetchall()
            )
    except (OSError, sqlite3.Error, TypeError, ValueError):
        return _result(
            database_present=True,
            database_size_bytes=None,
            reason_codes=("DATABASE_ACCESS_OR_SCHEMA_ERROR",),
        )

    reasons: list[str] = []
    if integrity != "ok":
        reasons.append("INTEGRITY_CHECK_FAILED")
    if foreign_keys:
        reasons.append("FOREIGN_KEY_VIOLATIONS_PRESENT")
    if items <= 0:
        reasons.append("NO_ITEMS")
    if snapshots <= 0:
        reasons.append("NO_SNAPSHOTS")
    if runs <= 0:
        reasons.append("NO_COLLECTION_RUNS")
    if not isinstance(oldest, str) or not isinstance(latest, str):
        reasons.append("OBSERVATION_RANGE_UNAVAILABLE")

    return _result(
        status=READY if not reasons else BLOCKED,
        database_present=True,
        database_size_bytes=size,
        items_count=items,
        item_snapshots_count=snapshots,
        collection_runs_count=runs,
        oldest_observed_at=oldest if isinstance(oldest, str) else None,
        latest_observed_at=latest if isinstance(latest, str) else None,
        average_observations_per_item=average,
        integrity_check=integrity,
        foreign_key_violation_count=foreign_keys,
        reason_codes=tuple(sorted(reasons)) if reasons else ("DB_BASELINE_READY",),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit the Revenue MVP database baseline without writes."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DATABASE_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    result = audit_database(parse_args(argv).db)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
