"""Aggregate-only readiness audit for ebook comic projection candidates."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

import category_collection_health as health
import ebook_comic_projection_candidate as projection


VERSION = "0.1"
READY = "READY_FOR_FIELD_AND_SEMANTICS_REVIEW"
FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class StructureBlockerAggregate:
    reason_code: str
    count: int


@dataclass(frozen=True)
class EbookComicProjectionReadinessAudit:
    version: str
    status: str
    item_count: int
    structure_ready_count: int
    structure_blocked_count: int
    blocker_reasons: tuple[StructureBlockerAggregate, ...]
    artifact_created: bool
    database_write_performed: bool
    contributor_semantics_confirmed: bool
    field_rights_confirmed: bool
    compliance_approved: bool
    publication_allowed: bool
    production_write_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["blocker_reasons"] = [asdict(row) for row in self.blocker_reasons]
        result["reason_codes"] = list(self.reason_codes)
        return result


def _failed(reason: str) -> EbookComicProjectionReadinessAudit:
    return EbookComicProjectionReadinessAudit(
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
        False,
        (reason,),
    )


def _public_id(source: dict[str, str]) -> str:
    canonical = "\x1f".join(
        source[key]
        for key in ("site", "service", "floor", "content_type", "content_id")
    )
    return "ebc_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def _candidate(row: sqlite3.Row) -> dict[str, Any]:
    source = {
        "site": row["site"],
        "service": row["service"],
        "floor": row["floor"],
        "content_type": row["content_type"],
        "content_id": row["content_id"],
    }
    contributors = json.loads(row["contributors_json"])
    image = json.loads(row["image_json"])
    return {
        "projection_version": projection.VERSION,
        "public_id": _public_id(source),
        "source": source,
        "title": row["title"],
        "release_date_raw": row["release_date_raw"],
        "current_price": row["current_price_min"],
        "list_price": row["list_price_min"],
        "authors": contributors.get("author", []) if isinstance(contributors, dict) else None,
        "manufactures": (
            contributors.get("manufacture", []) if isinstance(contributors, dict) else None
        ),
        "series": json.loads(row["series_json"]),
        "genres": json.loads(row["genre_json"]),
        "image": {
            "large": image.get("large") if isinstance(image, dict) else None,
            "list": image.get("list") if isinstance(image, dict) else None,
            "small": image.get("small") if isinstance(image, dict) else None,
        },
        "source_product_url": row["item_url"],
        "review": {
            "average": row["review_average"],
            "count": row["review_count"],
        },
        "observed_at": row["observed_at"],
        "data_freshness": "CURRENT",
    }


def assess(
    database: Path = health.DATABASE,
    config: Path = health.CONFIG,
) -> EbookComicProjectionReadinessAudit:
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
            "SELECT s.site,s.service,s.floor,s.content_type,i.content_id,i.title,"
            "i.release_date_raw,i.item_url,i.image_json,i.contributors_json,"
            "i.series_json,i.genre_json,x.observed_at,x.current_price_min,"
            "x.list_price_min,x.review_average,x.review_count "
            "FROM category_items i JOIN category_sources s ON s.source_id=i.source_id "
            "JOIN latest l ON l.item_id=i.item_id "
            "JOIN category_item_snapshots x ON x.snapshot_id=l.snapshot_id "
            "WHERE s.content_type='ebook_comic' ORDER BY i.item_id"
        ).fetchall()
        decisions = [projection.assess(_candidate(row)) for row in rows]
        ready_count = sum(result.status == projection.READY for result in decisions)
        blocker_counts = Counter(
            result.reason_codes[0]
            for result in decisions
            if result.status != projection.READY
        )
        blocker_reasons = tuple(
            StructureBlockerAggregate(reason, count)
            for reason, count in sorted(blocker_counts.items())
        )
        reasons = [
            "AGGREGATE_EBOOK_COMIC_STRUCTURE_READINESS_AUDITED",
            "FIELD_RIGHTS_AND_CONTRIBUTOR_SEMANTICS_REVIEW_REQUIRED",
            "PUBLICATION_REMAINS_CLOSED",
        ]
        if ready_count != len(rows):
            reasons.insert(1, "STRUCTURE_BLOCKERS_PRESENT")
        return EbookComicProjectionReadinessAudit(
            VERSION,
            READY,
            len(rows),
            ready_count,
            len(rows) - ready_count,
            blocker_reasons,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            tuple(reasons),
        )
    except Exception:
        return _failed("EBOOK_COMIC_PROJECTION_READINESS_AUDIT_ERROR")
    finally:
        if connection is not None:
            connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit aggregate ebook comic projection readiness without artifacts."
    )
    parser.add_argument("--database", type=Path, default=health.DATABASE)
    parser.add_argument("--config", type=Path, default=health.CONFIG)
    args = parser.parse_args(argv)
    result = assess(args.database, args.config)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
