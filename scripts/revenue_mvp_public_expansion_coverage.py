"""Read-only aggregate coverage audit for the staged 300-item expansion."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any


VERSION = "0.1"
TARGET_COUNT = 300
MAX_AGE = timedelta(hours=48)
READY = "COVERAGE_READY_FOR_SEPARATE_REVIEW"
BLOCKED = "BLOCKED"
FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class CoverageAudit:
    version: str
    status: str
    database_sha256: str | None
    target_count: int
    total_item_count: int
    snapshot_title_count: int
    official_image_count: int
    price_count: int
    affiliate_observation_count: int
    base_eligible_count: int
    fresh_base_eligible_count: int
    target_gap: int
    candidate_ids_exposed: bool
    publication_allowed: bool
    production_write_performed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(
    status: str,
    *,
    database_sha256: str | None = None,
    counts: tuple[int, int, int, int, int, int, int] = (0, 0, 0, 0, 0, 0, 0),
    reasons: tuple[str, ...],
) -> CoverageAudit:
    total, titles, images, prices, affiliate, eligible, fresh = counts
    return CoverageAudit(
        VERSION, status, database_sha256, TARGET_COUNT, total, titles, images,
        prices, affiliate, eligible, fresh, max(0, TARGET_COUNT - fresh),
        False, False, False, reasons,
    )


def _timestamp(value: Any) -> datetime:
    if type(value) is not str:
        raise ValueError("TIMESTAMP_INVALID")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    if parsed.tzinfo is None:
        raise ValueError("TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc)


def assess(database: Path, *, evaluated_at: datetime) -> CoverageAudit:
    connection: sqlite3.Connection | None = None
    try:
        if evaluated_at.tzinfo is None or database.is_symlink() or not database.is_file():
            return _result(status=FAIL_CLOSED, reasons=("INPUT_INVALID",))
        database_bytes = database.read_bytes()
        database_sha256 = hashlib.sha256(database_bytes).hexdigest()
        connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            return _result(status=FAIL_CLOSED, reasons=("DATABASE_INTEGRITY_FAILED",))
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            return _result(status=FAIL_CLOSED, reasons=("DATABASE_FOREIGN_KEY_FAILED",))

        rows = connection.execute("""
            WITH latest AS (
              SELECT s.*,
                     row_number() OVER (
                       PARTITION BY s.item_id
                       ORDER BY s.observed_at DESC, s.id DESC
                     ) AS latest_number
              FROM item_snapshots AS s
            )
            SELECT i.image_url_large, s.price_min, s.observed_at,
                   t.title, o.affiliate_link_observed,
                   o.source_status_code, o.reason_code
            FROM items AS i
            JOIN latest AS s ON s.item_id = i.id AND s.latest_number = 1
            LEFT JOIN item_snapshot_titles AS t
              ON t.snapshot_id = s.id AND t.observed_at = s.observed_at
            LEFT JOIN item_lifecycle_observations AS o ON o.snapshot_id = s.id
        """).fetchall()

        titles = images = prices = affiliate = eligible = fresh = 0
        now = evaluated_at.astimezone(timezone.utc)
        for row in rows:
            title_ready = type(row["title"]) is str and bool(row["title"])
            image_ready = (
                type(row["image_url_large"]) is str
                and row["image_url_large"].startswith("https://pics.dmm.co.jp/")
            )
            price_ready = type(row["price_min"]) is int and row["price_min"] >= 0
            affiliate_ready = (
                row["affiliate_link_observed"] == 1
                and row["source_status_code"] == 200
                and row["reason_code"] == "AFFILIATE_URL_VALIDATED"
            )
            titles += int(title_ready)
            images += int(image_ready)
            prices += int(price_ready)
            affiliate += int(affiliate_ready)
            base_ready = title_ready and image_ready and price_ready and affiliate_ready
            eligible += int(base_ready)
            if base_ready:
                age = now - _timestamp(row["observed_at"])
                fresh += int(timedelta(0) <= age <= MAX_AGE)

        counts = (len(rows), titles, images, prices, affiliate, eligible, fresh)
        if fresh < TARGET_COUNT:
            return _result(
                status=BLOCKED,
                database_sha256=database_sha256,
                counts=counts,
                reasons=("EXACT_300_FRESH_ELIGIBLE_ITEMS_UNAVAILABLE",),
            )
        return _result(
            status=READY,
            database_sha256=database_sha256,
            counts=counts,
            reasons=("AGGREGATE_COVERAGE_ONLY", "SEPARATE_EXACT_SELECTION_REQUIRED"),
        )
    except (OSError, sqlite3.Error, UnicodeError, ValueError):
        return _result(status=FAIL_CLOSED, reasons=("COVERAGE_AUDIT_FAILED",))
    finally:
        if connection is not None:
            connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--evaluated-at", required=True)
    args = parser.parse_args(argv)
    try:
        evaluated_at = _timestamp(args.evaluated_at)
    except ValueError:
        result = _result(status=FAIL_CLOSED, reasons=("INPUT_INVALID",))
    else:
        result = assess(args.db, evaluated_at=evaluated_at)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {READY, BLOCKED} else 2


if __name__ == "__main__":
    raise SystemExit(main())
