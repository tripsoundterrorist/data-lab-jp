"""Aggregate-only checkpoint for pausing doujin preparation safely."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

import category_collection_health as health
import doujin_compliance_followup_packet as followup
import doujin_compliance_handoff as compliance
import doujin_price_snapshot_audit as price_audit


VERSION = "0.1"
READY = "READY_TO_PAUSE_FOR_P0_REVIEW"
FAIL_CLOSED = "FAIL_CLOSED"
P0_REVIEW_NOT_BEFORE_JST = "2026-10-10"
P0_REVIEW_WINDOW_JST = "2026-10-02/2026-10-08"


@dataclass(frozen=True)
class DoujinPreparationCheckpoint:
    version: str
    status: str
    item_count: int
    projection_structure_blocked_count: int
    price_structure_blocked_count: int
    unresolved_official_question_ids: tuple[str, ...]
    unresolved_official_question_count: int
    p0_review_window_jst: str
    p0_review_not_before_jst: str
    external_send_performed: bool
    database_write_performed: bool
    repository_write_performed: bool
    compliance_approved: bool
    publication_allowed: bool
    production_write_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["unresolved_official_question_ids"] = list(
            self.unresolved_official_question_ids
        )
        result["reason_codes"] = list(self.reason_codes)
        return result


def _failed(reason: str) -> DoujinPreparationCheckpoint:
    return DoujinPreparationCheckpoint(
        VERSION,
        FAIL_CLOSED,
        0,
        0,
        0,
        (),
        0,
        P0_REVIEW_WINDOW_JST,
        P0_REVIEW_NOT_BEFORE_JST,
        False,
        False,
        False,
        False,
        False,
        False,
        (reason,),
    )


def compose(
    handoff: compliance.DoujinComplianceHandoff,
    prices: price_audit.DoujinPriceSnapshotAudit,
    packet: followup.DoujinComplianceFollowupPacket,
) -> DoujinPreparationCheckpoint:
    if (
        type(handoff) is not compliance.DoujinComplianceHandoff
        or type(prices) is not price_audit.DoujinPriceSnapshotAudit
        or type(packet) is not followup.DoujinComplianceFollowupPacket
        or handoff.status != compliance.READY
        or prices.status != price_audit.READY
        or packet.status != "READY_FOR_MANUAL_SEND_REVIEW"
        or handoff.item_count != prices.latest_snapshot_count
        or packet.question_count != len(packet.questions)
        or packet.send_authorized
        or packet.external_send_performed
        or handoff.compliance_approved
        or handoff.publication_allowed
        or prices.publication_allowed
    ):
        return _failed("DOUJIN_CHECKPOINT_INPUT_NOT_READY")
    question_ids = tuple(row.question_id for row in packet.questions)
    if len(set(question_ids)) != len(question_ids):
        return _failed("DOUJIN_CHECKPOINT_QUESTION_IDENTITY_INVALID")
    reasons = [
        "COLLECTION_ONLY_PREPARATION_CHECKPOINT_RECORDED",
        "P0_REVENUE_REVIEW_TAKES_PRIORITY",
        "MANUAL_COMPLIANCE_FOLLOWUP_REMAINS_UNSENT",
        "PUBLICATION_REMAINS_CLOSED",
    ]
    if handoff.structure_blocked_count or prices.structure_blocked_count:
        reasons.insert(1, "TECHNICAL_STRUCTURE_BLOCKERS_PRESENT")
    return DoujinPreparationCheckpoint(
        VERSION,
        READY,
        handoff.item_count,
        handoff.structure_blocked_count,
        prices.structure_blocked_count,
        question_ids,
        len(question_ids),
        P0_REVIEW_WINDOW_JST,
        P0_REVIEW_NOT_BEFORE_JST,
        False,
        False,
        False,
        False,
        False,
        False,
        tuple(reasons),
    )


def assess(
    database: Path = health.DATABASE,
    config: Path = health.CONFIG,
) -> DoujinPreparationCheckpoint:
    try:
        return compose(
            compliance.assess(database, config),
            price_audit.assess(database, config),
            followup.build(),
        )
    except Exception:
        return _failed("DOUJIN_PREPARATION_CHECKPOINT_ERROR")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a non-writing checkpoint before returning to P0 review."
    )
    parser.add_argument("--database", type=Path, default=health.DATABASE)
    parser.add_argument("--config", type=Path, default=health.CONFIG)
    args = parser.parse_args(argv)
    result = assess(args.database, args.config)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
