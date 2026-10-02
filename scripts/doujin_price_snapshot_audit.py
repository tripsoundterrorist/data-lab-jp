"""Read-only aggregate audit of latest normalized doujin price snapshots."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Any

import category_collection_health as health
import doujin_price_snapshot_candidate as candidate


VERSION = "0.1"
READY = "READY_FOR_PRICE_SEMANTICS_REVIEW"
FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class CategoryPriceAudit:
    content_type: str
    latest_snapshot_count: int
    structure_valid_count: int
    structure_blocked_count: int
    current_price_candidate_count: int
    discount_candidate_count: int
    price_unavailable_count: int


@dataclass(frozen=True)
class DoujinPriceSnapshotAudit:
    version: str
    status: str
    latest_snapshot_count: int
    structure_valid_count: int
    structure_blocked_count: int
    categories: tuple[CategoryPriceAudit, ...]
    price_values_emitted: bool
    database_write_performed: bool
    historical_retention_allowed: bool
    public_display_allowed: bool
    analysis_allowed: bool
    publication_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["categories"] = [asdict(row) for row in self.categories]
        result["reason_codes"] = list(self.reason_codes)
        return result


def _failed(reason: str) -> DoujinPriceSnapshotAudit:
    return DoujinPriceSnapshotAudit(
        VERSION,
        FAIL_CLOSED,
        0,
        0,
        0,
        (),
        False,
        False,
        False,
        False,
        False,
        False,
        (reason,),
    )


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def assess(
    database: Path = health.DATABASE,
    config: Path = health.CONFIG,
) -> DoujinPriceSnapshotAudit:
    baseline = health.assess(database, config)
    if baseline.status != health.HEALTHY:
        return _failed("CATEGORY_COLLECTION_HEALTH_NOT_READY")
    connection: sqlite3.Connection | None = None
    try:
        uri = f"file:{database.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "WITH latest AS ("
            "SELECT item_id,max(snapshot_id) AS snapshot_id "
            "FROM category_item_snapshots GROUP BY item_id) "
            "SELECT s.content_type,x.observed_at,x.current_price_min,"
            "x.list_price_min,x.discount_amount,x.discount_rate "
            "FROM category_items i JOIN category_sources s ON s.source_id=i.source_id "
            "JOIN latest l ON l.item_id=i.item_id "
            "JOIN category_item_snapshots x ON x.snapshot_id=l.snapshot_id "
            "WHERE s.content_type IN ('doujin','doujin_bl','doujin_tl') "
            "ORDER BY s.content_type,i.item_id"
        ).fetchall()
        counts = {
            content_type: {
                "total": 0,
                "valid": 0,
                "current": 0,
                "discount": 0,
                "unavailable": 0,
            }
            for content_type in candidate.CONTENT_TYPES
        }
        for row in rows:
            bucket = counts[row["content_type"]]
            bucket["total"] += 1
            observed_at = _timestamp(row["observed_at"])
            if observed_at is None:
                result = None
            else:
                result = candidate.assess_doujin_price_snapshot(
                    candidate.DoujinPriceObservation(
                        version=candidate.VERSION,
                        content_type=row["content_type"],
                        observed_at=observed_at,
                        current_price=row["current_price_min"],
                        list_price=row["list_price_min"],
                        discount_amount=row["discount_amount"],
                        discount_rate=row["discount_rate"],
                    )
                )
            if result is not None and result.normalized_price_structure_valid:
                bucket["valid"] += 1
                bucket["current"] += result.current_price_fact_candidate
                bucket["discount"] += result.discount_fact_candidate
                bucket["unavailable"] += not result.current_price_fact_candidate

        categories = tuple(
            CategoryPriceAudit(
                content_type=content_type,
                latest_snapshot_count=values["total"],
                structure_valid_count=values["valid"],
                structure_blocked_count=values["total"] - values["valid"],
                current_price_candidate_count=values["current"],
                discount_candidate_count=values["discount"],
                price_unavailable_count=values["unavailable"],
            )
            for content_type, values in sorted(counts.items())
        )
        total = sum(row.latest_snapshot_count for row in categories)
        valid = sum(row.structure_valid_count for row in categories)
        reasons = ["AGGREGATE_PRICE_STRUCTURE_AUDITED"]
        if valid != total:
            reasons.append("PRICE_STRUCTURE_BLOCKERS_PRESENT")
        reasons.extend(
            (
                "PRICE_SEMANTICS_REVIEW_REQUIRED",
                "HISTORICAL_RETENTION_UNCONFIRMED",
                "PUBLICATION_REMAINS_CLOSED",
            )
        )
        return DoujinPriceSnapshotAudit(
            VERSION,
            READY,
            total,
            valid,
            total - valid,
            categories,
            False,
            False,
            False,
            False,
            False,
            False,
            tuple(reasons),
        )
    except Exception:
        return _failed("DOUJIN_PRICE_SNAPSHOT_AUDIT_ERROR")
    finally:
        if connection is not None:
            connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit latest doujin price structure without emitting values."
    )
    parser.add_argument("--database", type=Path, default=health.DATABASE)
    parser.add_argument("--config", type=Path, default=health.CONFIG)
    args = parser.parse_args(argv)
    result = assess(args.database, args.config)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
