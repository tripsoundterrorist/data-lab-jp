"""Aggregate-only impact audit for the ebook comic review-pair policy candidate."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any

import category_collection_health as health
import ebook_comic_review_pair_policy_candidate as policy


VERSION = "0.1"
READY = "READY_FOR_NON_PUBLIC_POLICY_REVIEW"
FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class EbookComicReviewPairImpactAudit:
    version: str
    status: str
    item_count: int
    complete_pair_count: int
    absent_pair_count: int
    incomplete_pair_count: int
    invalid_pair_count: int
    omission_candidate_count: int
    artifact_created: bool
    database_write_performed: bool
    source_history_mutation_allowed: bool
    compliance_approved: bool
    publication_allowed: bool
    production_write_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["reason_codes"] = list(self.reason_codes)
        return result


def _result(
    *,
    status: str,
    counts: Counter[str] | None = None,
    reason_codes: tuple[str, ...],
) -> EbookComicReviewPairImpactAudit:
    values = counts or Counter()
    item_count = sum(values.values())
    return EbookComicReviewPairImpactAudit(
        VERSION,
        status,
        item_count,
        values["COMPLETE"],
        values["ABSENT"],
        values["INCOMPLETE"],
        values["INVALID"],
        values["ABSENT"] + values["INCOMPLETE"],
        False,
        False,
        False,
        False,
        False,
        False,
        reason_codes,
    )


def assess(
    database: Path = health.DATABASE,
    config: Path = health.CONFIG,
) -> EbookComicReviewPairImpactAudit:
    baseline = health.assess(database, config)
    if baseline.status != health.HEALTHY:
        return _result(
            status=FAIL_CLOSED,
            reason_codes=("CATEGORY_COLLECTION_HEALTH_NOT_READY",),
        )
    connection: sqlite3.Connection | None = None
    try:
        uri = f"file:{database.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        rows = connection.execute(
            "WITH latest AS ("
            "SELECT item_id,max(snapshot_id) AS snapshot_id "
            "FROM category_item_snapshots GROUP BY item_id) "
            "SELECT x.review_average,x.review_count "
            "FROM category_items i JOIN category_sources s ON s.source_id=i.source_id "
            "JOIN latest l ON l.item_id=i.item_id "
            "JOIN category_item_snapshots x ON x.snapshot_id=l.snapshot_id "
            "WHERE s.content_type='ebook_comic' ORDER BY i.item_id"
        ).fetchall()
        decisions = [policy.assess(average, count) for average, count in rows]
        counts = Counter(decision.source_state for decision in decisions)
        if counts["INVALID"]:
            return _result(
                status=FAIL_CLOSED,
                counts=counts,
                reason_codes=(
                    "INVALID_REVIEW_PAIR_PRESENT",
                    "PUBLICATION_REMAINS_CLOSED",
                ),
            )
        return _result(
            status=READY,
            counts=counts,
            reason_codes=(
                "AGGREGATE_REVIEW_PAIR_IMPACT_AUDITED",
                "INCOMPLETE_AND_ABSENT_PAIRS_OMITTED_ONLY_AS_CANDIDATE",
                "SOURCE_HISTORY_PRESERVED",
                "COMPLIANCE_REVIEW_REQUIRED",
                "PUBLICATION_REMAINS_CLOSED",
            ),
        )
    except Exception:
        return _result(
            status=FAIL_CLOSED,
            reason_codes=("REVIEW_PAIR_IMPACT_AUDIT_ERROR",),
        )
    finally:
        if connection is not None:
            connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit aggregate review-pair policy impact without artifacts."
    )
    parser.add_argument("--database", type=Path, default=health.DATABASE)
    parser.add_argument("--config", type=Path, default=health.CONFIG)
    args = parser.parse_args(argv)
    result = assess(args.database, args.config)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
