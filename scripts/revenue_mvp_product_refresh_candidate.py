"""Compose an offline product refresh candidate from existing fail-closed gates."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import revenue_mvp_product_card_reconciliation as cards
import revenue_mvp_product_refresh_rehearsal as rehearsal
import revenue_mvp_unordered_publication_candidate as renderer
import revenue_mvp_unordered_review_packet as packet_builder


VERSION = "0.1"
READY = "OFFLINE_REFRESH_CANDIDATE_READY"
BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class RefreshCandidateReceipt:
    version: str
    status: str
    source_db_sha256: str | None
    packet_sha256: str | None
    base_artifact_sha256: str | None
    candidate_sha256: str | None
    card_count: int
    image_count: int
    cta_count: int
    go_route_count: int
    candidate_written: bool
    publication_allowed: bool = False
    production_write_performed: bool = False
    d1_write_performed: bool = False
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(reason: str) -> RefreshCandidateReceipt:
    return RefreshCandidateReceipt(
        VERSION, BLOCKED, None, None, None, None, 0, 0, 0, 0, False,
        reason_codes=(reason,),
    )


def build_candidate(
    database: Path,
    expected_db_sha256: str,
    evaluated_at: datetime,
    output: Path,
    *,
    expected_count: int = 100,
) -> RefreshCandidateReceipt:
    """Write one review-only candidate outside the repository."""

    try:
        if evaluated_at.tzinfo is None or expected_count <= 0:
            return _blocked("INPUT_INVALID")
        packet = packet_builder.build_packet(
            database, expected_db_sha256, evaluated_at.astimezone(timezone.utc)
        )
        packet_value = json.loads(packet)
        if len(packet_value["candidates"]) != expected_count:
            return _blocked("PACKET_CANDIDATE_COUNT_INVALID")
        base, base_receipt = renderer.render(
            packet, evaluated_at=evaluated_at, target_route="/items/"
        )
        reconciled = cards.reconcile(base, database)
        if len(reconciled) != expected_count:
            return _blocked("CARD_RECONCILIATION_COUNT_INVALID")
        candidate = cards.enrich(
            base, database, frozenset(card.public_id for card in reconciled)
        )
        image_count = candidate.count(b'class="card-image"')
        cta_count = candidate.count(b'class="affiliate-cta-block"')
        route_count = candidate.count(b'href="/go/itm_')
        if (image_count, cta_count, route_count) != (
            expected_count, expected_count, expected_count,
        ):
            return _blocked("CANDIDATE_SURFACE_COUNT_INVALID")
        if base_receipt.artifact_sha256 != hashlib.sha256(base).hexdigest():
            return _blocked("BASE_ARTIFACT_IDENTITY_INVALID")

        renderer.write_candidate(output, candidate)
        final_check = rehearsal.assess(
            output, database, evaluated_at=evaluated_at,
            expected_count=expected_count,
        )
        if (
            final_check.status != "READY_FOR_SEPARATE_REFRESH_CANDIDATE"
            or final_check.candidate_count != expected_count
            or final_check.retained_count != expected_count
            or final_check.added_count != 0
            or final_check.removed_count != 0
        ):
            try:
                output.unlink()
            except OSError:
                pass
            return _blocked("FINAL_REHEARSAL_INVALID")
        return RefreshCandidateReceipt(
            VERSION, READY, expected_db_sha256,
            hashlib.sha256(packet).hexdigest(),
            hashlib.sha256(base).hexdigest(),
            hashlib.sha256(candidate).hexdigest(), expected_count,
            image_count, cta_count, route_count, True,
            reason_codes=(
                "OFFLINE_REVIEW_ONLY", "D1_VERIFICATION_REQUIRED",
                "EXPLICIT_PRODUCTION_APPROVAL_REQUIRED",
            ),
        )
    except (
        OSError, UnicodeError, ValueError, KeyError, TypeError,
        packet_builder.PacketFailure, renderer.CandidateFailure,
    ):
        return _blocked("CANDIDATE_BUILD_FAILED")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--expected-db-sha256", required=True)
    parser.add_argument("--evaluated-at", required=True, type=packet_builder.parse_timestamp)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-count", type=int, default=100)
    args = parser.parse_args(argv)
    result = build_candidate(
        args.db, args.expected_db_sha256, args.evaluated_at, args.output,
        expected_count=args.expected_count,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 1


if __name__ == "__main__":
    raise SystemExit(main())

