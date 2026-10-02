"""Read-only aggregate audit of isolated multi-category collection value."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any

import category_collection_health as health


VERSION = "0.1"
READY = "READY_FOR_COLLECTION_ONLY_REVIEW"
FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class CategoryAggregate:
    content_type: str
    item_count: int
    snapshot_count: int
    successful_run_count: int
    first_observed_at: str | None
    last_observed_at: str | None
    items_with_release_date: int
    items_with_contributors: int
    items_with_series: int
    items_with_genre: int
    items_with_price: int
    items_with_list_price: int
    items_with_discount: int
    items_with_review: int
    items_with_price_change: int


@dataclass(frozen=True)
class CategoryValueAudit:
    version: str
    status: str
    source_count: int
    item_count: int
    snapshot_count: int
    categories: tuple[CategoryAggregate, ...]
    publication_closed: bool
    database_write_performed: bool
    publication_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["categories"] = [asdict(row) for row in self.categories]
        value["reason_codes"] = list(self.reason_codes)
        return value


def _failed(reason: str) -> CategoryValueAudit:
    return CategoryValueAudit(
        VERSION, FAIL_CLOSED, 0, 0, 0, (), False, False, False, (reason,),
    )


def assess(
    database: Path = health.DATABASE,
    config: Path = health.CONFIG,
) -> CategoryValueAudit:
    baseline = health.assess(database, config)
    if baseline.status != health.HEALTHY:
        return _failed("CATEGORY_COLLECTION_HEALTH_NOT_READY")
    connection: sqlite3.Connection | None = None
    try:
        uri = f"file:{database.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        rows: list[CategoryAggregate] = []
        sources = connection.execute(
            "SELECT source_id,content_type FROM category_sources ORDER BY content_type"
        ).fetchall()
        for source_id, content_type in sources:
            item_row = connection.execute(
                "SELECT count(*),"
                "sum(release_date_raw IS NOT NULL),"
                "sum(contributors_json != '{}'),"
                "sum(json_array_length(series_json) > 0),"
                "sum(json_array_length(genre_json) > 0) "
                "FROM category_items WHERE source_id=?",
                (source_id,),
            ).fetchone()
            snapshot_row = connection.execute(
                "SELECT count(*),min(x.observed_at),max(x.observed_at),"
                "count(DISTINCT CASE WHEN x.current_price_min IS NOT NULL THEN x.item_id END),"
                "count(DISTINCT CASE WHEN x.list_price_min IS NOT NULL THEN x.item_id END),"
                "count(DISTINCT CASE WHEN x.discount_amount > 0 THEN x.item_id END),"
                "count(DISTINCT CASE WHEN x.review_count IS NOT NULL THEN x.item_id END) "
                "FROM category_item_snapshots x JOIN category_items i ON i.item_id=x.item_id "
                "WHERE i.source_id=?",
                (source_id,),
            ).fetchone()
            successful_runs = connection.execute(
                "SELECT count(*) FROM category_collection_runs "
                "WHERE source_id=? AND status='success'",
                (source_id,),
            ).fetchone()[0]
            changed_prices = connection.execute(
                "SELECT count(*) FROM ("
                "SELECT x.item_id FROM category_item_snapshots x "
                "JOIN category_items i ON i.item_id=x.item_id "
                "WHERE i.source_id=? AND x.current_price_min IS NOT NULL "
                "GROUP BY x.item_id HAVING count(DISTINCT x.current_price_min) > 1)",
                (source_id,),
            ).fetchone()[0]
            rows.append(CategoryAggregate(
                content_type=content_type,
                item_count=item_row[0],
                snapshot_count=snapshot_row[0],
                successful_run_count=successful_runs,
                first_observed_at=snapshot_row[1],
                last_observed_at=snapshot_row[2],
                items_with_release_date=item_row[1] or 0,
                items_with_contributors=item_row[2] or 0,
                items_with_series=item_row[3] or 0,
                items_with_genre=item_row[4] or 0,
                items_with_price=snapshot_row[3],
                items_with_list_price=snapshot_row[4],
                items_with_discount=snapshot_row[5],
                items_with_review=snapshot_row[6],
                items_with_price_change=changed_prices,
            ))
        return CategoryValueAudit(
            VERSION, READY, len(rows), sum(row.item_count for row in rows),
            sum(row.snapshot_count for row in rows), tuple(rows), True, False,
            False, ("AGGREGATE_COLLECTION_HISTORY_READY",),
        )
    except Exception:
        return _failed("CATEGORY_VALUE_AUDIT_ERROR")
    finally:
        if connection is not None:
            connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit aggregate collection-only category history without writes."
    )
    parser.add_argument("--database", type=Path, default=health.DATABASE)
    parser.add_argument("--config", type=Path, default=health.CONFIG)
    args = parser.parse_args(argv)
    result = assess(args.database, args.config)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
