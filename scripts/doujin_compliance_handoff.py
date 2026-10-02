"""Sanitized, non-sending handoff for doujin compliance scope review."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

import category_collection_health as health
import doujin_entity_integrity_audit as entity_audit
import doujin_projection_readiness_audit as projection_audit
import doujin_rights_scope_audit as rights_audit


VERSION = "0.1"
READY = "READY_FOR_COMPLIANCE_HANDOFF"
FAIL_CLOSED = "FAIL_CLOSED"

RIGHTS_SCOPE_QUESTIONS = (
    "DOUJIN_SOURCE_SCOPE_APPLICABILITY",
    "RELEASE_DATE_PUBLIC_DISPLAY",
    "LIST_PRICE_PUBLIC_DISPLAY",
    "OBSERVATION_TIME_PUBLIC_DISPLAY",
    "DATA_FRESHNESS_PUBLIC_DISPLAY",
)
RETENTION_QUESTIONS = (
    "SANITIZED_RAW_RETENTION_ALLOWED",
    "SANITIZED_RAW_RETENTION_DURATION",
    "HISTORICAL_NORMALIZED_PRICE_RETENTION",
    "PRODUCT_REMOVAL_RETENTION",
)
LIFECYCLE_QUESTIONS = (
    "API_VISIBLE_AFFILIATE_ELIGIBILITY",
    "API_INVISIBLE_PUBLICATION_ACTION",
    "PREORDER_AVAILABILITY_SEMANTICS",
)
IMAGE_LINK_QUESTIONS = (
    "DOUJIN_MAIN_IMAGE_DISPLAY_REQUIREMENTS",
    "DOUJIN_DEEPLINK_AFFILIATE_METHOD",
)
QUESTION_IDS = (
    *RIGHTS_SCOPE_QUESTIONS,
    *RETENTION_QUESTIONS,
    *LIFECYCLE_QUESTIONS,
    *IMAGE_LINK_QUESTIONS,
)


@dataclass(frozen=True)
class DoujinComplianceHandoff:
    version: str
    status: str
    item_count: int
    structure_ready_count: int
    structure_blocked_count: int
    question_ids: tuple[str, ...]
    question_count: int
    external_send_performed: bool
    repository_write_performed: bool
    compliance_approved: bool
    publication_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["question_ids"] = list(self.question_ids)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _failed(reason: str) -> DoujinComplianceHandoff:
    return DoujinComplianceHandoff(
        VERSION, FAIL_CLOSED, 0, 0, 0, (), 0, False, False, False, False,
        (reason,),
    )


def compose(
    entities: entity_audit.EntityIntegrityAudit,
    projection: projection_audit.ProjectionReadinessAudit,
    rights: rights_audit.DoujinRightsScopeAudit,
) -> DoujinComplianceHandoff:
    if (
        entities.status != entity_audit.READY
        or projection.status != projection_audit.READY
        or rights.status != rights_audit.READY
        or entities.item_count != projection.item_count
        or projection.structure_ready_count + projection.structure_blocked_count
        != projection.item_count
    ):
        return _failed("DOUJIN_COMPLIANCE_HANDOFF_INPUT_NOT_READY")
    reasons = [
        "TECHNICAL_PREPARATION_EVIDENCE_READY",
        "OFFICIAL_SCOPE_CONFIRMATION_REQUIRED",
        "NO_EXTERNAL_SEND",
        "PUBLICATION_REMAINS_CLOSED",
    ]
    if projection.structure_blocked_count:
        reasons.insert(1, "STRUCTURE_BLOCKERS_PRESENT")
    return DoujinComplianceHandoff(
        VERSION, READY, projection.item_count, projection.structure_ready_count,
        projection.structure_blocked_count, QUESTION_IDS, len(QUESTION_IDS),
        False, False, False, False, tuple(reasons),
    )


def assess(
    database: Path = health.DATABASE,
    config: Path = health.CONFIG,
) -> DoujinComplianceHandoff:
    try:
        return compose(
            entity_audit.assess(database, config),
            projection_audit.assess(database, config),
            rights_audit.assess(),
        )
    except Exception:
        return _failed("DOUJIN_COMPLIANCE_HANDOFF_ERROR")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a sanitized doujin compliance handoff without sending it."
    )
    parser.add_argument("--database", type=Path, default=health.DATABASE)
    parser.add_argument("--config", type=Path, default=health.CONFIG)
    args = parser.parse_args(argv)
    result = assess(args.database, args.config)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
