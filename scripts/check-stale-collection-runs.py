from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = ROOT / "data" / "data-lab.db"
DEFAULT_OLDER_THAN_MINUTES = 60
MIN_OLDER_THAN_MINUTES = 30
MAX_OLDER_THAN_MINUTES = 1440
REQUIRED_COLUMNS = {
    "collection_run_id",
    "run_type",
    "status",
    "started_at",
    "finished_at",
}
UTC_ISO_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$"
)


class StaleCheckFailure(Exception):
    pass


def bounded_minutes(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"must be an integer from {MIN_OLDER_THAN_MINUTES} "
            f"to {MAX_OLDER_THAN_MINUTES}"
        ) from error
    if parsed < MIN_OLDER_THAN_MINUTES or parsed > MAX_OLDER_THAN_MINUTES:
        raise argparse.ArgumentTypeError(
            f"must be an integer from {MIN_OLDER_THAN_MINUTES} "
            f"to {MAX_OLDER_THAN_MINUTES}"
        )
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect stale native collection runs without changing the DB."
    )
    parser.add_argument(
        "--older-than-minutes",
        type=bounded_minutes,
        default=DEFAULT_OLDER_THAN_MINUTES,
        help=f"stale candidate age in minutes (default: {DEFAULT_OLDER_THAN_MINUTES})",
    )
    return parser.parse_args(argv)


def parse_started_at(value: object) -> tuple[datetime | None, str | None]:
    if value is None:
        return None, "MISSING_STARTED_AT"
    if not isinstance(value, str) or not value.strip():
        return None, "INVALID_STARTED_AT"
    if not UTC_ISO_PATTERN.fullmatch(value):
        if re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?",
            value,
        ):
            return None, "TIMEZONE_REQUIRED"
        return None, "INVALID_STARTED_AT"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None, "INVALID_STARTED_AT"
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        return None, "NON_UTC_STARTED_AT"
    return parsed.astimezone(timezone.utc), None


def validate_schema(connection: sqlite3.Connection) -> None:
    table_exists = connection.execute(
        """
        SELECT 1 FROM sqlite_master
        WHERE type = 'table' AND name = 'collection_runs'
        """
    ).fetchone()
    if table_exists is None:
        raise StaleCheckFailure("COLLECTION_RUNS_TABLE_MISSING")
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(collection_runs)")
    }
    if not REQUIRED_COLUMNS.issubset(columns):
        raise StaleCheckFailure("COLLECTION_RUNS_COLUMNS_MISSING")


def inspect_connection(
    connection: sqlite3.Connection,
    older_than_minutes: int,
    now: datetime | None = None,
) -> tuple[int, list[tuple[str, str, int]], list[tuple[str, str]]]:
    validate_schema(connection)
    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        raise StaleCheckFailure("CHECK_TIME_NOT_TIMEZONE_AWARE")
    checked_at = checked_at.astimezone(timezone.utc)

    rows = connection.execute(
        """
        SELECT collection_run_id, started_at
        FROM collection_runs
        WHERE run_type = 'native'
          AND status = 'running'
          AND finished_at IS NULL
        ORDER BY collection_run_id
        """
    ).fetchall()
    stale_candidates: list[tuple[str, str, int]] = []
    anomalies: list[tuple[str, str]] = []

    for collection_run_id, started_at in rows:
        parsed, anomaly_code = parse_started_at(started_at)
        if anomaly_code is not None:
            anomalies.append((str(collection_run_id), anomaly_code))
            continue
        if parsed is None:
            raise StaleCheckFailure("STARTED_AT_PARSE_STATE_INVALID")

        elapsed_seconds = (checked_at - parsed).total_seconds()
        if elapsed_seconds < 0:
            anomalies.append((str(collection_run_id), "FUTURE_STARTED_AT"))
            continue
        if elapsed_seconds >= older_than_minutes * 60:
            stale_candidates.append(
                (str(collection_run_id), str(started_at), int(elapsed_seconds // 60))
            )

    return len(rows), stale_candidates, anomalies


def check_database(
    database_path: Path,
    older_than_minutes: int,
    now: datetime | None = None,
) -> tuple[int, list[tuple[str, str, int]], list[tuple[str, str]]]:
    resolved_path = database_path.resolve()
    if not resolved_path.is_file():
        raise StaleCheckFailure("DATABASE_NOT_FOUND")
    connection = sqlite3.connect(f"{resolved_path.as_uri()}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only = ON")
        return inspect_connection(connection, older_than_minutes, now)
    finally:
        connection.close()


def main() -> int:
    args = parse_args()
    try:
        checked_count, stale_candidates, anomalies = check_database(
            DATABASE_PATH, args.older_than_minutes
        )
    except StaleCheckFailure as error:
        print(f"stale check failed: {error}", file=sys.stderr)
        return 1
    except (OSError, sqlite3.Error):
        print("stale check failed: DATABASE_ACCESS_ERROR", file=sys.stderr)
        return 1
    except Exception:
        print("stale check failed: UNEXPECTED_ERROR", file=sys.stderr)
        return 1

    print(f"checked_running_runs: {checked_count}")
    print(f"stale_candidate_count: {len(stale_candidates)}")
    print(f"anomaly_count: {len(anomalies)}")
    for collection_run_id, started_at, elapsed_minutes in stale_candidates:
        print("stale_candidate:")
        print(f"  collection_run_id: {collection_run_id}")
        print(f"  started_at: {started_at}")
        print(f"  elapsed_minutes: {elapsed_minutes}")
    for collection_run_id, anomaly_code in anomalies:
        print("run_data_anomaly:")
        print(f"  collection_run_id: {collection_run_id}")
        print(f"  anomaly_code: {anomaly_code}")

    if anomalies:
        return 3
    if stale_candidates:
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("stale check failed: UNEXPECTED_ERROR", file=sys.stderr)
        raise SystemExit(1)
