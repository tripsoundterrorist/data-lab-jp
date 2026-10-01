"""Pure readiness gate for a future Revenue MVP ranking surface."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

import collection_policy


VERSION = "0.1"
READY_FOR_MANUAL_IMPLEMENTATION_REVIEW = "READY_FOR_MANUAL_IMPLEMENTATION_REVIEW"
BLOCKED = "BLOCKED"
FAIL_CLOSED = "FAIL_CLOSED"
SAFE_EXISTING_SORTS = (
    "original",
    "price-asc",
    "price-desc",
    "observed-desc",
    "observed-asc",
)
PROHIBITED_PUBLIC_LABELS = (
    "人気ランキング",
    "売れ筋ランキング",
    "公式ランキング",
    "総合ランキング",
)


@dataclass(frozen=True)
class RankingEvidence:
    official_sort_definition_confirmed: bool
    separate_population_collection_verified: bool
    temporal_stability_validated: bool
    database_schema_ready: bool
    collector_integration_tested: bool
    compliance_publication_confirmed: bool
    product_funnel_window_closed: bool
    product_funnel_review_completed: bool


@dataclass(frozen=True)
class RankingReadiness:
    version: str
    status: str
    implementation_review_candidate: bool
    publication_allowed: bool
    production_write_allowed: bool
    ranking_label_allowed: bool
    safe_existing_sorts: tuple[str, ...]
    prohibited_public_labels: tuple[str, ...]
    reason_codes: tuple[str, ...]
    next_actions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["safe_existing_sorts"] = list(self.safe_existing_sorts)
        value["prohibited_public_labels"] = list(self.prohibited_public_labels)
        value["reason_codes"] = list(self.reason_codes)
        value["next_actions"] = list(self.next_actions)
        return value


def assess(evidence: Any) -> RankingReadiness:
    if not isinstance(evidence, RankingEvidence) or any(
        type(getattr(evidence, field)) is not bool
        for field in RankingEvidence.__dataclass_fields__
    ):
        return RankingReadiness(
            VERSION, FAIL_CLOSED, False, False, False, False,
            SAFE_EXISTING_SORTS, PROHIBITED_PUBLIC_LABELS,
            ("EVIDENCE_INVALID",), ("PROVIDE_TYPED_CURRENT_EVIDENCE",),
        )

    try:
        policy = collection_policy.rank_candidate_policy()
        evaluated = collection_policy.evaluate_collection_policy(policy)
    except Exception:
        return RankingReadiness(
            VERSION, FAIL_CLOSED, False, False, False, False,
            SAFE_EXISTING_SORTS, PROHIBITED_PUBLIC_LABELS,
            ("POLICY_EVALUATION_FAILED",), ("REVIEW_COLLECTION_POLICY",),
        )

    checks = {
        "OFFICIAL_SORT_DEFINITION_UNCONFIRMED": evidence.official_sort_definition_confirmed,
        "SEPARATE_RANK_POPULATION_UNVERIFIED": evidence.separate_population_collection_verified,
        "TEMPORAL_STABILITY_UNVALIDATED": evidence.temporal_stability_validated,
        "DATABASE_SCHEMA_NOT_READY": evidence.database_schema_ready,
        "COLLECTOR_INTEGRATION_UNTESTED": evidence.collector_integration_tested,
        "COMPLIANCE_PUBLICATION_UNCONFIRMED": evidence.compliance_publication_confirmed,
        "PRODUCT_FUNNEL_WINDOW_NOT_CLOSED": evidence.product_funnel_window_closed,
        "PRODUCT_FUNNEL_REVIEW_NOT_COMPLETED": evidence.product_funnel_review_completed,
    }
    reasons = {reason for reason, passed in checks.items() if passed is not True}
    if not evaluated.valid:
        reasons.add("RANK_COLLECTION_POLICY_INVALID")
    if evaluated.production_collection_eligible is not True:
        reasons.add("RANK_COLLECTION_NOT_PRODUCTION_ELIGIBLE")

    ready = not reasons
    next_actions = []
    if not evidence.official_sort_definition_confirmed:
        next_actions.append("CONFIRM_OFFICIAL_RANK_SORT_MEANING")
    if not evidence.separate_population_collection_verified:
        next_actions.append("VALIDATE_ISOLATED_RANK_POPULATION_COLLECTION")
    if not evidence.temporal_stability_validated:
        next_actions.append("COMPLETE_TEMPORAL_STABILITY_REVIEW")
    if not evidence.database_schema_ready or not evidence.collector_integration_tested:
        next_actions.append("REVIEW_NON_DESTRUCTIVE_DATA_HANDOFF")
    if not evidence.compliance_publication_confirmed:
        next_actions.append("OBTAIN_COMPLIANCE_PUBLICATION_DECISION")
    if not evidence.product_funnel_window_closed:
        next_actions.append("WAIT_FOR_CLOSED_PRODUCT_FUNNEL_WINDOW")
    if not evidence.product_funnel_review_completed:
        next_actions.append("COMPLETE_PRODUCT_FUNNEL_REVIEW")

    return RankingReadiness(
        VERSION,
        READY_FOR_MANUAL_IMPLEMENTATION_REVIEW if ready else BLOCKED,
        ready,
        False,
        False,
        False,
        SAFE_EXISTING_SORTS,
        PROHIBITED_PUBLIC_LABELS,
        tuple(sorted(reasons)),
        tuple(dict.fromkeys(next_actions)),
    )


def current_evidence() -> RankingEvidence:
    return RankingEvidence(False, False, False, False, False, False, False, False)


def main() -> int:
    result = assess(current_evidence())
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {BLOCKED, READY_FOR_MANUAL_IMPLEMENTATION_REVIEW} else 2


if __name__ == "__main__":
    raise SystemExit(main())
