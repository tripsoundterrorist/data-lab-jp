"""Read-only fail-closed rehearsal for refreshing the live product surface.

The rehearsal compares the currently rendered cards with the newest bounded
collector run.  It emits aggregate counts only and never writes the database,
the site artifact, D1, or a publication Gate.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any

from revenue_mvp_lifecycle_receipt import public_item_id
from revenue_mvp_product_card_reconciliation import reconcile


VERSION = "0.1"
MAX_AGE = timedelta(hours=48)


@dataclass(frozen=True)
class RefreshRehearsal:
    version: str
    status: str
    current_card_count: int | None
    candidate_count: int | None
    retained_count: int | None
    added_count: int | None
    removed_count: int | None
    candidate_observed_at: str | None
    candidate_age_seconds: int | None
    affiliate_eligible_count: int | None
    d1_refresh_required: bool
    artifact_refresh_required: bool
    publication_allowed: bool
    production_write_performed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(reason: str) -> RefreshRehearsal:
    return RefreshRehearsal(
        VERSION, "BLOCKED", None, None, None, None, None, None, None, None,
        False, False, False, False, (reason,),
    )


def _timestamp(value: Any) -> datetime:
    if type(value) is not str:
        raise ValueError("TIMESTAMP_INVALID")
    parsed = datetime.fromisoformat(
        value[:-1] + "+00:00" if value.endswith("Z") else value
    )
    if parsed.tzinfo is None:
        raise ValueError("TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc)


def assess(
    source: Path,
    database: Path,
    *,
    evaluated_at: datetime | None = None,
    expected_count: int = 100,
) -> RefreshRehearsal:
    connection: sqlite3.Connection | None = None
    try:
        if source.is_symlink() or database.is_symlink() or expected_count <= 0:
            return _blocked("INPUT_INVALID")
        current = reconcile(source.read_bytes(), database)
        if len(current) != expected_count:
            return _blocked("CURRENT_CARD_COUNT_INVALID")

        connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            return _blocked("DATABASE_INTEGRITY_FAILED")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            return _blocked("DATABASE_FOREIGN_KEY_FAILED")

        run = connection.execute("""
            SELECT collection_run_id, started_at, status, processed_items,
                   snapshots_inserted, api_calls, pages_fetched
            FROM collection_runs
            WHERE run_type = 'native'
            ORDER BY started_at DESC
            LIMIT 1
        """).fetchone()
        if (
            run is None or run["status"] != "success"
            or run["processed_items"] != expected_count
            or run["snapshots_inserted"] != expected_count
            or type(run["api_calls"]) is not int or run["api_calls"] <= 0
            or type(run["pages_fetched"]) is not int or run["pages_fetched"] <= 0
        ):
            return _blocked("LATEST_COLLECTION_RUN_INVALID")

        rows = connection.execute("""
            SELECT i.site, i.service, i.floor, i.content_id, i.image_url_large,
                   s.price_min, s.observed_at, t.title,
                   o.affiliate_link_observed, o.source_status_code
            FROM item_snapshots AS s
            JOIN items AS i ON i.id = s.item_id
            JOIN item_snapshot_titles AS t
              ON t.snapshot_id = s.id AND t.observed_at = s.observed_at
            JOIN item_lifecycle_observations AS o ON o.snapshot_id = s.id
            WHERE s.collection_run_id = ?
            ORDER BY s.source_position, s.id
        """, (run["collection_run_id"],)).fetchall()
        if len(rows) != expected_count:
            return _blocked("LATEST_CANDIDATE_COUNT_INVALID")

        public_ids: set[str] = set()
        observed_values: set[str] = set()
        eligible = 0
        for row in rows:
            identity = (row["site"], row["service"], row["floor"], row["content_id"])
            if not all(type(value) is str and value for value in identity):
                return _blocked("CANDIDATE_IDENTITY_INVALID")
            if (
                type(row["title"]) is not str or not row["title"]
                or type(row["price_min"]) is not int or row["price_min"] < 0
                or type(row["image_url_large"]) is not str
                or not row["image_url_large"].startswith("https://pics.dmm.co.jp/")
                or row["affiliate_link_observed"] != 1
                or row["source_status_code"] != 200
            ):
                return _blocked("CANDIDATE_PUBLICATION_INPUT_INVALID")
            public_ids.add(public_item_id(*identity))
            observed_values.add(row["observed_at"])
            eligible += 1
        if len(public_ids) != expected_count or len(observed_values) != 1:
            return _blocked("CANDIDATE_UNIQUENESS_INVALID")

        observed_at = next(iter(observed_values))
        observed = _timestamp(observed_at)
        now = (evaluated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        age = int((now - observed).total_seconds())
        if age < 0 or age > int(MAX_AGE.total_seconds()):
            return _blocked("CANDIDATE_FRESHNESS_INVALID")

        current_ids = {card.public_id for card in current}
        retained = len(current_ids & public_ids)
        added = len(public_ids - current_ids)
        removed = len(current_ids - public_ids)
        reasons = ["PUBLICATION_REMAINS_CLOSED"]
        if added or removed:
            reasons.extend(("D1_REFRESH_REQUIRED", "ARTIFACT_REFRESH_REQUIRED"))
        else:
            reasons.append("ARTIFACT_REFRESH_REQUIRED")
        return RefreshRehearsal(
            VERSION, "READY_FOR_SEPARATE_REFRESH_CANDIDATE", len(current),
            len(rows), retained, added, removed, observed_at, age, eligible,
            bool(added or removed), True, False, False, tuple(reasons),
        )
    except (OSError, UnicodeError, sqlite3.Error, ValueError):
        return _blocked("REFRESH_REHEARSAL_FAILED")
    finally:
        if connection is not None:
            connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--expected-count", type=int, default=100)
    args = parser.parse_args()
    result = assess(args.source, args.db, expected_count=args.expected_count)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == "READY_FOR_SEPARATE_REFRESH_CANDIDATE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
