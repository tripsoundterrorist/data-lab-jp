from __future__ import annotations

import argparse
import sys
from pathlib import Path

from collector_preflight import (
    DEFAULT_OLDER_THAN_MINUTES,
    MAX_OLDER_THAN_MINUTES,
    MIN_OLDER_THAN_MINUTES,
    run_preflight,
)


ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = ROOT / "data" / "data-lab.db"
ENV_PATH = ROOT / ".env"


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
        description="Run the collector safety preflight without changing the DB."
    )
    parser.add_argument(
        "--older-than-minutes",
        type=bounded_minutes,
        default=DEFAULT_OLDER_THAN_MINUTES,
        help=f"stale candidate age in minutes (default: {DEFAULT_OLDER_THAN_MINUTES})",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    result = run_preflight(
        DATABASE_PATH,
        ENV_PATH,
        older_than_minutes=args.older_than_minutes,
    )
    print(f"ready: {str(result.ready).lower()}")
    print(f"result_code: {result.error_code}")
    print(f"checked_running_runs: {result.checked_running_runs}")
    print(f"stale_candidate_count: {result.stale_candidate_count}")
    print(f"anomaly_count: {result.anomaly_count}")
    if result.disk_free_bytes is not None:
        print(f"disk_free_mib: {result.disk_free_bytes // (1024 * 1024)}")
    return result.exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("preflight failed: UNEXPECTED_ERROR", file=sys.stderr)
        raise SystemExit(1)
