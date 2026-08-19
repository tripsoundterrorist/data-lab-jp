from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from collector_preflight import (
    DEFAULT_OLDER_THAN_MINUTES,
    MAX_OLDER_THAN_MINUTES,
    MIN_OLDER_THAN_MINUTES,
    PreflightProcessingError,
    analyze_running_rows,
    read_running_rows,
)


ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = ROOT / "data" / "data-lab.db"


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


def inspect_connection(
    connection: sqlite3.Connection,
    older_than_minutes: int,
    now: datetime | None = None,
) -> tuple[int, list[tuple[str, str, int]], list[tuple[str, str]]]:
    rows = read_running_rows(connection)
    stale_candidates, anomalies = analyze_running_rows(
        rows, older_than_minutes, now
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
    except (StaleCheckFailure, PreflightProcessingError) as error:
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
