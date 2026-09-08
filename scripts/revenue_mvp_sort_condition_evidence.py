"""Read-only evidence for fail-closed DMM sort condition handling."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
from typing import Any

import collection_policy
import official_blocker_policy


VERSION = "0.1"
EVIDENCE_READY = "IMPLEMENTATION_EVIDENCE_READY"
BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class SortConditionEvidence:
    version: str
    status: str
    implementation_evidence_candidate: bool
    official_semantics_resolved: bool
    publication_gate_unlock_allowed: bool
    checks_passed: int
    checks_required: int
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def assess_sort_condition_evidence() -> SortConditionEvidence:
    """Exercise bounded policy properties without collecting or promoting."""

    try:
        rank = collection_policy.rank_candidate_policy()
        review = collection_policy.review_candidate_policy(
            include_second_page=True
        )
        rank_result = collection_policy.evaluate_collection_policy(rank)
        review_result = collection_policy.evaluate_collection_policy(review)
        unsafe_rank = collection_policy.evaluate_collection_policy(
            replace(rank, position_semantics="global popularity rank")
        )
        unsafe_review = collection_policy.evaluate_collection_policy(
            replace(review, review_sort_semantics="average descending")
        )
        complete_gates = collection_policy.evaluate_collection_policy(
            replace(
                rank,
                eligibility_gates=collection_policy.ProductionEligibilityGates(
                    True, True, True, True, True, True, True
                ),
            )
        )
        blocker = official_blocker_policy.blocker_for(
            official_blocker_policy.SORT_BLOCKER
        )
        checks = (
            rank_result.valid
            and rank.enabled is False
            and rank.experimental is True
            and rank_result.production_collection_eligible is False,
            review_result.valid
            and review.enabled is False
            and review.experimental is True
            and review_result.production_collection_eligible is False,
            not unsafe_rank.valid
            and "INVALID_RANK_SEMANTICS" in unsafe_rank.reason_codes,
            not unsafe_review.valid
            and "UNCONFIRMED_REVIEW_SEMANTICS" in unsafe_review.reason_codes,
            complete_gates.valid
            and complete_gates.production_collection_eligible is False,
            blocker.status
            == official_blocker_policy.PENDING_OFFICIAL_CONFIRMATION
            and blocker.gate_unlock_allowed is False,
        )
        passed = sum(check is True for check in checks)
        ready = passed == len(checks)
        return SortConditionEvidence(
            VERSION,
            EVIDENCE_READY if ready else BLOCKED,
            ready,
            False,
            False,
            passed,
            len(checks),
            (
                "FAIL_CLOSED_SORT_CONDITIONS_VERIFIED",
                "SEPARATE_OFFICIAL_SORT_SEMANTICS_REQUIRED",
            ) if ready else ("SORT_CONDITION_EVIDENCE_INCOMPLETE",),
        )
    except Exception:
        return SortConditionEvidence(
            VERSION, BLOCKED, False, False, False, 0, 6,
            ("SORT_CONDITION_EVIDENCE_INTERNAL_ERROR",),
        )


def main() -> int:
    result = assess_sort_condition_evidence()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == EVIDENCE_READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
