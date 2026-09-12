"""Read-only, sanitized health Gate for the isolated category collector."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data" / "category-collection.db"
CONFIG = ROOT / "config" / "category-collection-v0.1.json"
VERSION = "0.1"
HEALTHY = "COLLECTION_HEALTHY"
FAIL_CLOSED = "FAIL_CLOSED"
MAX_AGE_SECONDS = 26 * 60 * 60


@dataclass(frozen=True)
class CategoryCollectionHealth:
    version: str
    status: str
    source_count: int
    item_count: int
    snapshot_count: int
    successful_run_count: int
    latest_failed_source_count: int
    stale_source_count: int
    foreign_key_violation_count: int
    integrity_ok: bool
    publication_closed: bool
    database_write_performed: bool
    publication_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["reason_codes"] = list(self.reason_codes)
        return result


def _failed(reason: str) -> CategoryCollectionHealth:
    return CategoryCollectionHealth(
        VERSION, FAIL_CLOSED, 0, 0, 0, 0, 0, 0, 0,
        False, False, False, False, (reason,),
    )


def _timestamp(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed.astimezone(timezone.utc)


def assess(
    database: Path = DATABASE,
    config: Path = CONFIG,
    *,
    evaluated_at: datetime | None = None,
) -> CategoryCollectionHealth:
    connection: sqlite3.Connection | None = None
    try:
        now = evaluated_at or datetime.now(timezone.utc)
        if now.tzinfo is None or database.is_symlink() or config.is_symlink():
            return _failed("INPUT_INVALID")
        settings = json.loads(config.read_text(encoding="utf-8"))
        targets = settings.get("targets") if isinstance(settings, dict) else None
        if settings.get("mode") != "COLLECTION_ONLY" or not isinstance(targets, list):
            return _failed("CONFIG_INVALID")
        expected = {
            (target["content_type"], target["site"], target["service"], target["floor"])
            for target in targets
        }
        if len(expected) != len(targets) or not expected:
            return _failed("CONFIG_INVALID")

        uri = f"file:{database.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        integrity_ok = connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        foreign_keys = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        actual = set(connection.execute(
            "SELECT content_type,site,service,floor FROM category_sources"
        ).fetchall())
        source_count = len(actual)
        item_count = connection.execute("SELECT count(*) FROM category_items").fetchone()[0]
        snapshot_count = connection.execute(
            "SELECT count(*) FROM category_item_snapshots"
        ).fetchone()[0]
        success_count = connection.execute(
            "SELECT count(*) FROM category_collection_runs WHERE status='success'"
        ).fetchone()[0]
        latest_statuses = connection.execute(
            "SELECT r.status FROM category_collection_runs r WHERE NOT EXISTS ("
            "SELECT 1 FROM category_collection_runs newer "
            "WHERE newer.source_id=r.source_id AND "
            "(newer.started_at > r.started_at OR "
            "(newer.started_at=r.started_at AND newer.run_id > r.run_id)))"
        ).fetchall()
        failed_count = sum(status == "failed" for (status,) in latest_statuses)
        running_count = sum(status == "running" for (status,) in latest_statuses)
        open_rows = sum(connection.execute(
            "SELECT (SELECT count(*) FROM category_sources WHERE publication_allowed != 0) + "
            "(SELECT count(*) FROM category_collection_runs WHERE publication_allowed != 0) + "
            "(SELECT count(*) FROM category_items WHERE publication_allowed != 0) + "
            "(SELECT count(*) FROM category_item_snapshots WHERE publication_allowed != 0)"
        ).fetchone())
        latest = connection.execute(
            "SELECT s.content_type, max(r.finished_at) FROM category_sources s "
            "LEFT JOIN category_collection_runs r ON r.source_id=s.source_id "
            "AND r.status='success' GROUP BY s.source_id"
        ).fetchall()
        stale = 0
        for _content_type, finished_at in latest:
            if finished_at is None:
                stale += 1
                continue
            observed = _timestamp(finished_at)
            age = (now.astimezone(timezone.utc) - observed).total_seconds()
            if age < 0 or age > MAX_AGE_SECONDS:
                stale += 1

        reasons: list[str] = []
        if actual != expected:
            reasons.append("SOURCE_SET_MISMATCH")
        if not integrity_ok:
            reasons.append("INTEGRITY_CHECK_FAILED")
        if foreign_keys:
            reasons.append("FOREIGN_KEY_VIOLATION")
        if running_count:
            reasons.append("RUN_INCOMPLETE")
        if failed_count:
            reasons.append("FAILED_RUN_PRESENT")
        if stale:
            reasons.append("SOURCE_STALE")
        if open_rows:
            reasons.append("PUBLICATION_BOUNDARY_OPEN")
        if item_count <= 0 or snapshot_count <= 0 or success_count < source_count:
            reasons.append("COLLECTION_EVIDENCE_INSUFFICIENT")
        healthy = not reasons
        return CategoryCollectionHealth(
            VERSION, HEALTHY if healthy else FAIL_CLOSED, source_count,
            item_count, snapshot_count, success_count, failed_count, stale,
            foreign_keys, integrity_ok, open_rows == 0, False, False,
            tuple(reasons) or ("ISOLATED_COLLECTION_VERIFIED",),
        )
    except Exception:
        return _failed("HEALTH_CHECK_ERROR")
    finally:
        if connection is not None:
            connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit isolated category collection state")
    parser.add_argument("--database", type=Path, default=DATABASE)
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--evaluated-at", type=_timestamp)
    args = parser.parse_args(argv)
    result = assess(args.database, args.config, evaluated_at=args.evaluated_at)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == HEALTHY else 2


if __name__ == "__main__":
    raise SystemExit(main())
