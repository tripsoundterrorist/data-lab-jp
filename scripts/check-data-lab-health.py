from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collector_preflight import (
    PreflightProcessingError,
    analyze_running_rows,
    read_running_rows,
)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = ROOT / "data" / "data-lab.db"
BACKUP_DIRECTORY = ROOT / "data" / "backups" / "daily"
STALE_THRESHOLD_MINUTES = 60

TASK_NAMES = {
    "collector": "DATA LAB Daily Collector",
    "backup": "DATA LAB Daily Backup",
    "stale_check": "DATA LAB Daily Stale Check",
}

SEVERITY = {"OK": 0, "WARN": 1, "ERROR": 2}
NOT_YET_RUN_RESULT = 267011


class HealthInternalError(Exception):
    pass


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print("health check failed: INVALID_ARGUMENT", file=sys.stderr)
        raise SystemExit(3)


def add_issue(issues: list[dict[str, str]], level: str, code: str) -> None:
    issues.append({"level": level, "code": code})


def overall_status(issues: list[dict[str, str]]) -> str:
    highest = max((SEVERITY[issue["level"]] for issue in issues), default=0)
    return next(name for name, value in SEVERITY.items() if value == highest)


def read_only_connection(path: Path) -> sqlite3.Connection:
    resolved = path.resolve()
    connection = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def scalar(connection: sqlite3.Connection, sql: str) -> int:
    row = connection.execute(sql).fetchone()
    if row is None:
        raise HealthInternalError("DATABASE_QUERY_FAILURE")
    return int(row[0])


def parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def check_database(
    database_path: Path, issues: list[dict[str, str]]
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any]]:
    database: dict[str, Any] = {
        "path_exists": database_path.is_file(),
        "size_bytes": None,
        "integrity": "unavailable",
        "foreign_key_violations": None,
        "items": None,
        "item_snapshots": None,
        "collection_runs": None,
        "native_runs": None,
        "legacy_runs": None,
        "running_native": None,
        "failed_native": None,
        "orphan_items": None,
        "orphan_collection_runs": None,
        "snapshot_unique_duplicates": None,
    }
    stale = {
        "threshold_minutes": STALE_THRESHOLD_MINUTES,
        "running_native": None,
        "stale_count": None,
        "anomaly_count": None,
    }
    if not database_path.is_file():
        add_issue(issues, "ERROR", "DATABASE_MISSING")
        return database, None, stale

    try:
        database["size_bytes"] = database_path.stat().st_size
        with closing(read_only_connection(database_path)) as connection:
            integrity_rows = [
                str(row[0]) for row in connection.execute("PRAGMA integrity_check")
            ]
            database["integrity"] = (
                "ok" if integrity_rows == ["ok"] else "failed"
            )
            foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
            database["foreign_key_violations"] = len(foreign_key_rows)
            database["items"] = scalar(connection, "SELECT COUNT(*) FROM items")
            database["item_snapshots"] = scalar(
                connection, "SELECT COUNT(*) FROM item_snapshots"
            )
            database["collection_runs"] = scalar(
                connection, "SELECT COUNT(*) FROM collection_runs"
            )
            database["native_runs"] = scalar(
                connection,
                "SELECT COUNT(*) FROM collection_runs WHERE run_type = 'native'",
            )
            database["legacy_runs"] = scalar(
                connection,
                "SELECT COUNT(*) FROM collection_runs "
                "WHERE run_type = 'legacy_migrated'",
            )
            database["running_native"] = scalar(
                connection,
                """
                SELECT COUNT(*) FROM collection_runs
                WHERE run_type = 'native'
                  AND status = 'running'
                  AND finished_at IS NULL
                """,
            )
            database["failed_native"] = scalar(
                connection,
                "SELECT COUNT(*) FROM collection_runs "
                "WHERE run_type = 'native' AND status = 'failed'",
            )
            database["orphan_items"] = scalar(
                connection,
                """
                SELECT COUNT(*) FROM item_snapshots AS s
                LEFT JOIN items AS i ON i.id = s.item_id
                WHERE i.id IS NULL
                """,
            )
            database["orphan_collection_runs"] = scalar(
                connection,
                """
                SELECT COUNT(*) FROM item_snapshots AS s
                LEFT JOIN collection_runs AS r
                  ON r.collection_run_id = s.collection_run_id
                WHERE r.collection_run_id IS NULL
                """,
            )
            database["snapshot_unique_duplicates"] = scalar(
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

            latest_row = connection.execute(
                """
                SELECT collection_run_id, status, started_at, finished_at,
                       source_sort, fetched_items, snapshots_inserted, api_calls,
                       collection_complete, stop_reason, error_code,
                       first_observed_at, last_observed_at
                FROM collection_runs
                WHERE run_type = 'native'
                ORDER BY started_at DESC, collection_run_id DESC
                LIMIT 1
                """
            ).fetchone()
            latest_collection = None
            if latest_row is not None:
                keys = (
                    "collection_run_id",
                    "status",
                    "started_at",
                    "finished_at",
                    "source_sort",
                    "fetched_items",
                    "snapshots_inserted",
                    "api_calls",
                    "collection_complete",
                    "stop_reason",
                    "error_code",
                    "first_observed_at",
                    "last_observed_at",
                )
                latest_collection = dict(zip(keys, latest_row))

            running_rows = read_running_rows(connection)
            stale_candidates, anomalies = analyze_running_rows(
                running_rows, STALE_THRESHOLD_MINUTES
            )
            stale = {
                "threshold_minutes": STALE_THRESHOLD_MINUTES,
                "running_native": len(running_rows),
                "stale_count": len(stale_candidates),
                "anomaly_count": len(anomalies),
            }
    except (OSError, sqlite3.Error, HealthInternalError, PreflightProcessingError):
        database["integrity"] = "unavailable"
        add_issue(issues, "ERROR", "DATABASE_ACCESS_OR_SCHEMA_ERROR")
        return database, None, stale

    if database["integrity"] != "ok":
        add_issue(issues, "ERROR", "DATABASE_INTEGRITY_FAILURE")
    if database["foreign_key_violations"]:
        add_issue(issues, "ERROR", "DATABASE_FOREIGN_KEY_FAILURE")
    if database["orphan_items"]:
        add_issue(issues, "ERROR", "ORPHAN_ITEM_DETECTED")
    if database["orphan_collection_runs"]:
        add_issue(issues, "ERROR", "ORPHAN_COLLECTION_RUN_DETECTED")
    if database["snapshot_unique_duplicates"]:
        add_issue(issues, "ERROR", "SNAPSHOT_UNIQUE_DUPLICATE")
    if stale["anomaly_count"]:
        add_issue(issues, "ERROR", "RUN_TIMESTAMP_ANOMALY")
    if stale["stale_count"]:
        add_issue(issues, "ERROR", "STALE_NATIVE_RUN")
    elif stale["running_native"]:
        add_issue(issues, "WARN", "ACTIVE_NATIVE_RUN")
    if latest_collection and latest_collection["status"] == "failed":
        add_issue(issues, "WARN", "LATEST_NATIVE_RUN_FAILED")

    return database, latest_collection, stale


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def latest_collection_time(latest_collection: dict[str, Any] | None) -> datetime | None:
    if latest_collection is None:
        return None
    for key in ("finished_at", "last_observed_at", "started_at", "first_observed_at"):
        parsed = parse_utc(latest_collection.get(key))
        if parsed is not None:
            return parsed
    return None


def check_backup(
    source_database: dict[str, Any],
    latest_collection: dict[str, Any] | None,
    issues: list[dict[str, str]],
) -> dict[str, Any]:
    backup: dict[str, Any] = {
        "status": "missing",
        "count": 0,
        "latest_file": None,
        "latest_created_at": None,
        "latest_size_bytes": None,
        "latest_sha256": None,
        "integrity": None,
        "foreign_key_violations": None,
        "items": None,
        "item_snapshots": None,
        "collection_runs": None,
        "items_match_source": None,
        "snapshots_match_source": None,
        "collection_runs_match_source": None,
    }
    try:
        candidates = sorted(
            (
                path
                for path in BACKUP_DIRECTORY.glob("data-lab-*.db")
                if path.is_file()
            ),
            key=lambda path: (path.stat().st_mtime_ns, path.name),
            reverse=True,
        )
    except OSError:
        backup["status"] = "invalid"
        add_issue(issues, "ERROR", "BACKUP_DIRECTORY_ACCESS_ERROR")
        return backup

    backup["count"] = len(candidates)
    if not candidates:
        add_issue(issues, "WARN", "BACKUP_MISSING")
        return backup

    latest = candidates[0]
    backup["latest_file"] = latest.name
    try:
        stat = latest.stat()
        backup_time = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
        backup["latest_created_at"] = backup_time.isoformat().replace("+00:00", "Z")
        backup["latest_size_bytes"] = stat.st_size
        backup["latest_sha256"] = sha256_file(latest)
        with closing(read_only_connection(latest)) as connection:
            integrity_rows = [
                str(row[0]) for row in connection.execute("PRAGMA integrity_check")
            ]
            backup["integrity"] = (
                "ok" if integrity_rows == ["ok"] else "failed"
            )
            backup["foreign_key_violations"] = len(
                connection.execute("PRAGMA foreign_key_check").fetchall()
            )
            backup["items"] = scalar(connection, "SELECT COUNT(*) FROM items")
            backup["item_snapshots"] = scalar(
                connection, "SELECT COUNT(*) FROM item_snapshots"
            )
            backup["collection_runs"] = scalar(
                connection, "SELECT COUNT(*) FROM collection_runs"
            )
    except (OSError, sqlite3.Error, HealthInternalError):
        backup["status"] = "invalid"
        add_issue(issues, "ERROR", "LATEST_BACKUP_INVALID")
        return backup

    backup["items_match_source"] = backup["items"] == source_database["items"]
    backup["snapshots_match_source"] = (
        backup["item_snapshots"] == source_database["item_snapshots"]
    )
    backup["collection_runs_match_source"] = (
        backup["collection_runs"] == source_database["collection_runs"]
    )

    if backup["integrity"] != "ok" or backup["foreign_key_violations"]:
        backup["status"] = "invalid"
        add_issue(issues, "ERROR", "LATEST_BACKUP_INVALID")
        return backup

    collection_time = latest_collection_time(latest_collection)
    if collection_time is not None and backup_time < collection_time:
        backup["status"] = "older_than_latest_collection"
        add_issue(issues, "WARN", "BACKUP_OLDER_THAN_LATEST_COLLECTION")
    elif not all(
        (
            backup["items_match_source"],
            backup["snapshots_match_source"],
            backup["collection_runs_match_source"],
        )
    ):
        backup["status"] = "count_mismatch"
        add_issue(issues, "WARN", "BACKUP_COUNT_MISMATCH")
    else:
        backup["status"] = "current"
    return backup


def task_query_script() -> str:
    names = ",".join(f"'{name}'" for name in TASK_NAMES.values())
    return f"""
$ErrorActionPreference = 'Stop'
$names = @({names})
$result = [ordered]@{{}}
try {{
  foreach ($name in $names) {{
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($null -eq $task) {{
      $result[$name] = [ordered]@{{ exists = $false }}
      continue
    }}
    $info = Get-ScheduledTaskInfo -TaskName $name -ErrorAction Stop
    $result[$name] = [ordered]@{{
      exists = $true
      enabled = [bool]$task.Settings.Enabled
      state = [string]$task.State
      next_run = $info.NextRunTime.ToString('o')
      last_run = $info.LastRunTime.ToString('o')
      last_result = [int64]$info.LastTaskResult
    }}
  }}
  $result | ConvertTo-Json -Depth 4 -Compress
}} catch {{
  [Console]::Error.WriteLine('TASK_QUERY_FAILED')
  exit 1
}}
"""


def decode_process_output(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "cp932"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def check_tasks(issues: list[dict[str, str]]) -> dict[str, Any]:
    encoded = base64.b64encode(task_query_script().encode("utf-16le")).decode("ascii")
    try:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-EncodedCommand",
                encoded,
            ],
            cwd=ROOT,
            capture_output=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise HealthInternalError("TASK_QUERY_FAILED") from None
    if completed.returncode != 0:
        raise HealthInternalError("TASK_QUERY_FAILED")
    try:
        stdout = decode_process_output(completed.stdout)
        raw = json.loads(stdout.strip().lstrip("\ufeff"))
    except (json.JSONDecodeError, TypeError):
        raise HealthInternalError("TASK_QUERY_INVALID_OUTPUT") from None

    tasks: dict[str, Any] = {}
    for key, task_name in TASK_NAMES.items():
        task = raw.get(task_name, {"exists": False})
        tasks[key] = {"task_name": task_name, **task}
        if not task.get("exists"):
            level = "WARN" if key == "stale_check" else "ERROR"
            add_issue(issues, level, f"TASK_{key.upper()}_MISSING")
            continue
        if not task.get("enabled"):
            level = "WARN" if key == "stale_check" else "ERROR"
            add_issue(issues, level, f"TASK_{key.upper()}_DISABLED")
        last_result = task.get("last_result")
        if last_result not in (0, NOT_YET_RUN_RESULT):
            add_issue(issues, "WARN", f"TASK_{key.upper()}_LAST_RESULT_NONZERO")
    return tasks


def run_git(*arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(ROOT), *arguments],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise HealthInternalError("GIT_QUERY_FAILED") from None
    if completed.returncode != 0:
        raise HealthInternalError("GIT_QUERY_FAILED")
    return completed.stdout.strip()


def check_git(issues: list[dict[str, str]]) -> dict[str, Any]:
    branch = run_git("branch", "--show-current")
    porcelain_text = run_git("status", "--porcelain=v1")
    head = run_git("rev-parse", "HEAD")
    local_main = run_git("rev-parse", "refs/heads/main")
    origin_main = run_git("rev-parse", "refs/remotes/origin/main")
    porcelain = porcelain_text.splitlines() if porcelain_text else []
    clean = not porcelain
    synced = local_main == origin_main
    if not clean:
        add_issue(issues, "WARN", "GIT_WORKTREE_DIRTY")
    if not synced:
        add_issue(issues, "WARN", "LOCAL_MAIN_NOT_SYNCED_WITH_ORIGIN_MAIN")
    return {
        "branch": branch,
        "clean": clean,
        "status_porcelain": porcelain,
        "head": head,
        "local_main": local_main,
        "origin_main": origin_main,
        "synced_with_origin_main": synced,
    }


def collect_health(database_path: Path) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    database, latest_collection, stale = check_database(database_path, issues)
    backup = check_backup(database, latest_collection, issues)
    tasks = check_tasks(issues)
    git = check_git(issues)
    return {
        "overall": overall_status(issues),
        "database": database,
        "latest_collection": latest_collection,
        "stale_monitor": stale,
        "backup": backup,
        "tasks": tasks,
        "git": git,
        "issues": issues,
    }


def display_task(task: dict[str, Any]) -> str:
    if not task.get("exists"):
        return "not registered"
    last_result = task.get("last_result")
    last = "not yet run" if last_result == NOT_YET_RUN_RESULT else str(last_result)
    return f"{task.get('state', 'unknown')} / last={last}"


def print_human(result: dict[str, Any]) -> None:
    database = result["database"]
    latest = result["latest_collection"]
    backup = result["backup"]
    tasks = result["tasks"]
    git = result["git"]

    print("DATA LAB HEALTH CHECK")
    print(f"Overall: {result['overall']}")
    print()
    print("Database:")
    print(f"  integrity: {database['integrity']}")
    fk = database["foreign_key_violations"]
    print(f"  foreign_keys: {'ok' if fk == 0 else fk}")
    print(f"  items: {database['items']}")
    print(f"  snapshots: {database['item_snapshots']}")
    print(f"  collection_runs: {database['collection_runs']}")
    print(f"  running_native: {database['running_native']}")
    print()
    print("Latest collection:")
    if latest is None:
        print("  status: none")
    else:
        print(f"  collection_run_id: {latest['collection_run_id']}")
        print(f"  status: {latest['status']}")
        print(f"  snapshots_inserted: {latest['snapshots_inserted']}")
        print(f"  stop_reason: {latest['stop_reason']}")
    print()
    print("Backup:")
    print(f"  status: {backup['status']}")
    print(f"  backups: {backup['count']}")
    print(f"  latest: {backup['latest_file']}")
    print()
    print("Tasks:")
    print(f"  Collector: {display_task(tasks['collector'])}")
    print(f"  Backup: {display_task(tasks['backup'])}")
    print(f"  Stale Check: {display_task(tasks['stale_check'])}")
    print()
    print("Git:")
    print(f"  branch: {git['branch']}")
    print(f"  clean: {'yes' if git['clean'] else 'no'}")
    print(
        "  synced_with_origin_main: "
        f"{'yes' if git['synced_with_origin_main'] else 'no'}"
    )
    if result["issues"]:
        print()
        print("Issues:")
        for issue in result["issues"]:
            print(f"  {issue['level']}: {issue['code']}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = SafeArgumentParser(description="Read-only DATA LAB operational health check.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = collect_health(args.db.resolve())
    except HealthInternalError as error:
        result = {
            "overall": "ERROR",
            "error_code": str(error),
            "issues": [{"level": "ERROR", "code": "HEALTH_CHECK_INTERNAL_ERROR"}],
        }
        if args.json:
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        else:
            print("DATA LAB HEALTH CHECK")
            print("Overall: ERROR")
            print("health check failed: INTERNAL_ERROR", file=sys.stderr)
        return 3
    except Exception:
        if args.json:
            print(
                json.dumps(
                    {
                        "overall": "ERROR",
                        "error_code": "UNEXPECTED_ERROR",
                        "issues": [
                            {"level": "ERROR", "code": "HEALTH_CHECK_INTERNAL_ERROR"}
                        ],
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
        else:
            print("DATA LAB HEALTH CHECK")
            print("Overall: ERROR")
            print("health check failed: INTERNAL_ERROR", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    else:
        print_human(result)
    return {"OK": 0, "WARN": 1, "ERROR": 2}[result["overall"]]


if __name__ == "__main__":
    raise SystemExit(main())
