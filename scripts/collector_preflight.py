from __future__ import annotations

import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable


EXIT_READY = 0
EXIT_INTERNAL_ERROR = 1
EXIT_ACTIVE_RUN = 2
EXIT_STALE_OR_ANOMALY = 3
EXIT_DB_INTEGRITY = 4
EXIT_SCHEMA_MISMATCH = 5
EXIT_CLAIM_FAILURE = 6
EXIT_ENV_INVALID = 7
EXIT_DISK_INVALID = 8

DEFAULT_OLDER_THAN_MINUTES = 60
MIN_OLDER_THAN_MINUTES = 30
MAX_OLDER_THAN_MINUTES = 1440
MIN_FREE_BYTES = 256 * 1024 * 1024

REQUIRED_ENV_KEYS = ("DMM_API_ID", "DMM_AFFILIATE_ID")
REQUIRED_COLUMNS = {
    "items": {
        "id", "site", "service", "floor", "content_id", "product_id",
        "title", "source_date", "maker_json", "series_json", "actress_json",
        "genre_json", "image_url_large", "item_url", "first_observed_at",
        "last_observed_at", "master_updated_at",
    },
    "collection_runs": {
        "collection_run_id", "run_type", "started_at", "finished_at",
        "first_observed_at", "last_observed_at", "site", "service", "floor",
        "source_sort", "hits", "max_items", "max_pages", "api_calls",
        "pages_fetched", "api_total_count_initial", "total_count_changed",
        "fetched_items", "processed_items",
        "duplicate_content_ids_across_pages", "items_upserted",
        "snapshots_inserted", "collection_complete", "status", "stop_reason",
        "error_code",
    },
    "item_snapshots": {
        "id", "item_id", "collection_run_id", "observed_at", "source_sort",
        "source_offset", "source_position", "price_raw", "price_min",
        "review_average", "review_count", "query_context_json",
    },
}
UTC_ISO_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$"
)


@dataclass(frozen=True)
class PreflightResult:
    ready: bool
    exit_code: int
    error_code: str
    checked_running_runs: int = 0
    stale_candidate_count: int = 0
    anomaly_count: int = 0
    disk_free_bytes: int | None = None


@dataclass(frozen=True)
class ClaimResult:
    claimed: bool
    exit_code: int
    error_code: str


@dataclass(frozen=True)
class NativeRunClaim:
    collection_run_id: str
    started_at: str
    site: str
    service: str
    floor: str
    source_sort: str
    hits: int
    max_items: int
    max_pages: int


class PreflightProcessingError(Exception):
    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


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


def analyze_running_rows(
    rows: Iterable[tuple[object, object]],
    older_than_minutes: int,
    now: datetime | None = None,
) -> tuple[list[tuple[str, str, int]], list[tuple[str, str]]]:
    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None or checked_at.utcoffset() is None:
        raise PreflightProcessingError("CHECK_TIME_NOT_TIMEZONE_AWARE")
    checked_at = checked_at.astimezone(timezone.utc)
    stale_candidates: list[tuple[str, str, int]] = []
    anomalies: list[tuple[str, str]] = []
    for collection_run_id, started_at in rows:
        parsed, anomaly_code = parse_started_at(started_at)
        if anomaly_code is not None:
            anomalies.append((str(collection_run_id), anomaly_code))
            continue
        if parsed is None:
            raise PreflightProcessingError("STARTED_AT_PARSE_STATE_INVALID")
        elapsed_seconds = (checked_at - parsed).total_seconds()
        if elapsed_seconds < 0:
            anomalies.append((str(collection_run_id), "FUTURE_STARTED_AT"))
        elif elapsed_seconds >= older_than_minutes * 60:
            stale_candidates.append(
                (str(collection_run_id), str(started_at), int(elapsed_seconds // 60))
            )
    return stale_candidates, anomalies


def validate_running_schema(connection: sqlite3.Connection) -> None:
    columns = _table_columns(connection, "collection_runs")
    required = {"collection_run_id", "run_type", "status", "started_at", "finished_at"}
    if not required.issubset(columns):
        raise PreflightProcessingError("COLLECTION_RUNS_SCHEMA_MISSING")


def read_running_rows(connection: sqlite3.Connection) -> list[tuple[object, object]]:
    validate_running_schema(connection)
    return connection.execute(
        """
        SELECT collection_run_id, started_at
        FROM collection_runs
        WHERE run_type = 'native'
          AND status = 'running'
          AND finished_at IS NULL
        ORDER BY collection_run_id
        """
    ).fetchall()


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def _has_unique_columns(
    connection: sqlite3.Connection, table: str, expected: tuple[str, ...]
) -> bool:
    for row in connection.execute(f"PRAGMA index_list({table})"):
        if not row[2]:
            continue
        columns = tuple(
            item[2]
            for item in connection.execute(f"PRAGMA index_info({row[1]})")
        )
        if columns == expected:
            return True
    return False


def _has_foreign_key(
    connection: sqlite3.Connection,
    table: str,
    source_column: str,
    target_table: str,
    target_column: str,
    on_delete: str,
) -> bool:
    return any(
        row[2] == target_table
        and row[3] == source_column
        and row[4] == target_column
        and str(row[6]).upper() == on_delete
        for row in connection.execute(f"PRAGMA foreign_key_list({table})")
    )


def inspect_schema(connection: sqlite3.Connection) -> tuple[str | None, str | None]:
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    if not set(REQUIRED_COLUMNS).issubset(tables):
        return "REQUIRED_TABLE_MISSING", None
    for table, required in REQUIRED_COLUMNS.items():
        if not required.issubset(_table_columns(connection, table)):
            return "REQUIRED_COLUMN_MISSING", None

    structural_mismatch = False
    strict_rows = {
        row[0]: row[1]
        for row in connection.execute(
            "SELECT name, strict FROM pragma_table_list"
        )
    }
    if any(strict_rows.get(table) != 1 for table in REQUIRED_COLUMNS):
        structural_mismatch = True
    if not _has_unique_columns(
        connection, "items", ("site", "service", "floor", "content_id")
    ):
        structural_mismatch = True
    if not _has_unique_columns(
        connection,
        "item_snapshots",
        ("collection_run_id", "source_offset", "source_position"),
    ):
        structural_mismatch = True
    if not _has_foreign_key(
        connection, "item_snapshots", "item_id", "items", "id", "CASCADE"
    ):
        structural_mismatch = True
    if not _has_foreign_key(
        connection,
        "item_snapshots",
        "collection_run_id",
        "collection_runs",
        "collection_run_id",
        "RESTRICT",
    ):
        structural_mismatch = True
    collection_pk = {
        row[1]: row[5]
        for row in connection.execute("PRAGMA table_info(collection_runs)")
    }
    if collection_pk.get("collection_run_id") != 1:
        structural_mismatch = True
    return None, "REQUIRED_STRUCTURE_MISMATCH" if structural_mismatch else None


def validate_env_file(env_path: Path) -> str | None:
    if not env_path.is_file():
        return "ENV_FILE_MISSING"
    try:
        lines = env_path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return "ENV_FILE_UNREADABLE"
    values: dict[str, list[str]] = {key: [] for key in REQUIRED_ENV_KEYS}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in values:
            values[key].append(value.strip())
    for key in REQUIRED_ENV_KEYS:
        if len(values[key]) != 1:
            return "ENV_REQUIRED_KEY_MISSING_OR_DUPLICATE"
        if not values[key][0]:
            return "ENV_REQUIRED_VALUE_EMPTY"
    return None


def inspect_data_integrity(connection: sqlite3.Connection) -> str | None:
    integrity_rows = [str(row[0]) for row in connection.execute("PRAGMA integrity_check")]
    if integrity_rows != ["ok"]:
        return "INTEGRITY_CHECK_FAILED"
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        return "FOREIGN_KEY_CHECK_FAILED"
    if connection.execute(
        """
        SELECT 1 FROM item_snapshots AS s
        LEFT JOIN items AS i ON i.id = s.item_id
        WHERE i.id IS NULL LIMIT 1
        """
    ).fetchone() is not None:
        return "ORPHAN_ITEM_FOUND"
    if connection.execute(
        """
        SELECT 1 FROM item_snapshots AS s
        LEFT JOIN collection_runs AS r
          ON r.collection_run_id = s.collection_run_id
        WHERE r.collection_run_id IS NULL LIMIT 1
        """
    ).fetchone() is not None:
        return "ORPHAN_COLLECTION_RUN_FOUND"
    if connection.execute(
        """
        SELECT 1 FROM item_snapshots
        GROUP BY collection_run_id, source_offset, source_position
        HAVING COUNT(*) > 1 LIMIT 1
        """
    ).fetchone() is not None:
        return "SNAPSHOT_UNIQUE_DUPLICATE"
    return None


def run_preflight(
    database_path: Path,
    env_path: Path,
    older_than_minutes: int = DEFAULT_OLDER_THAN_MINUTES,
    minimum_free_bytes: int = MIN_FREE_BYTES,
    now: datetime | None = None,
    disk_free_provider: Callable[[Path], int] | None = None,
) -> PreflightResult:
    env_error = validate_env_file(env_path)
    if env_error is not None:
        return PreflightResult(False, EXIT_ENV_INVALID, env_error)
    resolved_database = database_path.resolve()
    if not resolved_database.is_file():
        return PreflightResult(False, EXIT_SCHEMA_MISMATCH, "DATABASE_NOT_FOUND")

    try:
        connection = sqlite3.connect(
            f"{resolved_database.as_uri()}?mode=ro", uri=True
        )
        try:
            connection.execute("PRAGMA query_only = ON")
            critical_schema_error, structural_schema_error = inspect_schema(connection)
            if critical_schema_error is not None:
                return PreflightResult(
                    False, EXIT_SCHEMA_MISMATCH, critical_schema_error
                )
            integrity_error = inspect_data_integrity(connection)
            if integrity_error is not None:
                return PreflightResult(False, EXIT_DB_INTEGRITY, integrity_error)
            if structural_schema_error is not None:
                return PreflightResult(
                    False, EXIT_SCHEMA_MISMATCH, structural_schema_error
                )
            running_rows = read_running_rows(connection)
        finally:
            connection.close()
        stale_candidates, anomalies = analyze_running_rows(
            running_rows, older_than_minutes, now
        )
        if stale_candidates or anomalies:
            return PreflightResult(
                False,
                EXIT_STALE_OR_ANOMALY,
                "STALE_OR_ANOMALOUS_RUNNING_RUN",
                len(running_rows),
                len(stale_candidates),
                len(anomalies),
            )
        if running_rows:
            return PreflightResult(
                False,
                EXIT_ACTIVE_RUN,
                "ACTIVE_NATIVE_RUN_EXISTS",
                len(running_rows),
            )
        provider = disk_free_provider or (lambda path: shutil.disk_usage(path).free)
        try:
            free_bytes = provider(resolved_database.parent)
        except Exception:
            return PreflightResult(
                False, EXIT_DISK_INVALID, "DISK_SPACE_UNAVAILABLE"
            )
        if isinstance(free_bytes, bool) or not isinstance(free_bytes, int):
            return PreflightResult(
                False, EXIT_DISK_INVALID, "DISK_SPACE_VALUE_INVALID"
            )
        if free_bytes < minimum_free_bytes:
            return PreflightResult(
                False,
                EXIT_DISK_INVALID,
                "DISK_SPACE_INSUFFICIENT",
                disk_free_bytes=free_bytes,
            )
        return PreflightResult(
            True,
            EXIT_READY,
            "READY",
            disk_free_bytes=free_bytes,
        )
    except PreflightProcessingError as error:
        return PreflightResult(False, EXIT_INTERNAL_ERROR, error.error_code)
    except (OSError, sqlite3.Error):
        return PreflightResult(False, EXIT_INTERNAL_ERROR, "PREFLIGHT_ACCESS_ERROR")
    except Exception:
        return PreflightResult(False, EXIT_INTERNAL_ERROR, "PREFLIGHT_UNEXPECTED_ERROR")


def claim_native_run(
    connection: sqlite3.Connection, claim: NativeRunClaim
) -> ClaimResult:
    try:
        connection.execute("BEGIN IMMEDIATE")
        active_count = connection.execute(
            """
            SELECT COUNT(*) FROM collection_runs
            WHERE run_type = 'native'
              AND status = 'running'
              AND finished_at IS NULL
            """
        ).fetchone()[0]
        if active_count:
            connection.rollback()
            return ClaimResult(False, EXIT_ACTIVE_RUN, "ACTIVE_NATIVE_RUN_EXISTS")
        connection.execute(
            """
            INSERT INTO collection_runs (
              collection_run_id, run_type, started_at, site, service, floor,
              source_sort, hits, max_items, max_pages, status
            ) VALUES (?, 'native', ?, ?, ?, ?, ?, ?, ?, ?, 'running')
            """,
            (
                claim.collection_run_id,
                claim.started_at,
                claim.site,
                claim.service,
                claim.floor,
                claim.source_sort,
                claim.hits,
                claim.max_items,
                claim.max_pages,
            ),
        )
        connection.commit()
        return ClaimResult(True, EXIT_READY, "CLAIMED")
    except sqlite3.Error:
        try:
            connection.rollback()
        except sqlite3.Error:
            pass
        return ClaimResult(False, EXIT_CLAIM_FAILURE, "DB_CLAIM_FAILED")
