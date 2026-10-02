"""Deterministic, non-public sequencing audit for collected categories."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

import category_collection_health as health
import category_collection_value_audit as value_audit


VERSION = "0.1"
READY = "READY_FOR_TECHNICAL_PREPARATION_REVIEW"
FAIL_CLOSED = "FAIL_CLOSED"
DOUJIN_FAMILY = frozenset({"doujin", "doujin_bl", "doujin_tl"})
MINIMUM_ITEMS = 100
MINIMUM_SUCCESSFUL_RUNS = 20
MINIMUM_CORE_COVERAGE = 0.95


@dataclass(frozen=True)
class PreparationCandidate:
    content_type: str
    item_count: int
    snapshot_count: int
    successful_run_count: int
    release_date_coverage: float
    contributor_coverage: float
    series_coverage: float
    genre_coverage: float
    price_coverage: float
    review_coverage: float
    observed_price_change_count: int
    technical_preparation_candidate: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class CategoryNextPreparationAudit:
    version: str
    status: str
    candidate_count: int
    recommended_content_type: str | None
    candidates: tuple[PreparationCandidate, ...]
    recommendation_scope: str
    revenue_priority_confirmed: bool
    compliance_approved: bool
    collection_change_allowed: bool
    publication_allowed: bool
    production_write_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["candidates"] = [
            {**asdict(row), "reason_codes": list(row.reason_codes)}
            for row in self.candidates
        ]
        result["reason_codes"] = list(self.reason_codes)
        return result


def _failed(reason: str) -> CategoryNextPreparationAudit:
    return CategoryNextPreparationAudit(
        VERSION,
        FAIL_CLOSED,
        0,
        None,
        (),
        "TECHNICAL_PREPARATION_ONLY",
        False,
        False,
        False,
        False,
        False,
        (reason,),
    )


def _coverage(count: int, total: int) -> float:
    return round(count / total, 6) if total > 0 else 0.0


def compose(audit: Any) -> CategoryNextPreparationAudit:
    if type(audit) is not value_audit.CategoryValueAudit or audit.status != value_audit.READY:
        return _failed("CATEGORY_VALUE_AUDIT_NOT_READY")
    candidates: list[PreparationCandidate] = []
    for row in audit.categories:
        if row.content_type in DOUJIN_FAMILY:
            continue
        coverages = {
            "release": _coverage(row.items_with_release_date, row.item_count),
            "contributor": _coverage(row.items_with_contributors, row.item_count),
            "series": _coverage(row.items_with_series, row.item_count),
            "genre": _coverage(row.items_with_genre, row.item_count),
            "price": _coverage(row.items_with_price, row.item_count),
            "review": _coverage(row.items_with_review, row.item_count),
        }
        eligible = (
            row.item_count >= MINIMUM_ITEMS
            and row.successful_run_count >= MINIMUM_SUCCESSFUL_RUNS
            and all(
                coverages[key] >= MINIMUM_CORE_COVERAGE
                for key in ("release", "contributor", "series", "genre", "price")
            )
        )
        reasons = []
        if row.item_count < MINIMUM_ITEMS:
            reasons.append("ITEM_SAMPLE_BELOW_TECHNICAL_THRESHOLD")
        if row.successful_run_count < MINIMUM_SUCCESSFUL_RUNS:
            reasons.append("COLLECTION_RUNS_BELOW_TECHNICAL_THRESHOLD")
        if not all(
            coverages[key] >= MINIMUM_CORE_COVERAGE
            for key in ("release", "contributor", "series", "genre", "price")
        ):
            reasons.append("CORE_METADATA_COVERAGE_BELOW_THRESHOLD")
        if eligible:
            reasons.append("TECHNICAL_PREPARATION_THRESHOLD_MET")
        reasons.append("REVENUE_AND_COMPLIANCE_NOT_EVALUATED")
        candidates.append(
            PreparationCandidate(
                row.content_type,
                row.item_count,
                row.snapshot_count,
                row.successful_run_count,
                coverages["release"],
                coverages["contributor"],
                coverages["series"],
                coverages["genre"],
                coverages["price"],
                coverages["review"],
                row.items_with_price_change,
                eligible,
                tuple(reasons),
            )
        )
    ordered = tuple(
        sorted(
            candidates,
            key=lambda row: (
                not row.technical_preparation_candidate,
                -row.item_count,
                row.content_type,
            ),
        )
    )
    recommended = next(
        (row.content_type for row in ordered if row.technical_preparation_candidate),
        None,
    )
    return CategoryNextPreparationAudit(
        VERSION,
        READY,
        sum(row.technical_preparation_candidate for row in ordered),
        recommended,
        ordered,
        "TECHNICAL_PREPARATION_ONLY",
        False,
        False,
        False,
        False,
        False,
        (
            "DETERMINISTIC_COLLECTION_EVIDENCE_ONLY",
            "ITEM_COUNT_BREAKS_TECHNICAL_TIES",
            "REVENUE_AND_COMPLIANCE_REQUIRE_SEPARATE_REVIEW",
            "PUBLICATION_REMAINS_CLOSED",
        ),
    )


def assess(
    database: Path = health.DATABASE,
    config: Path = health.CONFIG,
) -> CategoryNextPreparationAudit:
    try:
        return compose(value_audit.assess(database, config))
    except Exception:
        return _failed("CATEGORY_NEXT_PREPARATION_AUDIT_ERROR")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sequence future category technical preparation without publishing."
    )
    parser.add_argument("--database", type=Path, default=health.DATABASE)
    parser.add_argument("--config", type=Path, default=health.CONFIG)
    args = parser.parse_args(argv)
    result = assess(args.database, args.config)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
