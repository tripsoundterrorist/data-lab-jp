"""Pure, non-executing plan for expanding date collection toward 300 items."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from typing import Any

import collection_policy


VERSION = "0.1"
TARGET_COUNT = 300
HITS = 50
PROPOSED_REQUEST_COUNT = 6
READY = "READY_FOR_EXPLICIT_ISOLATED_COLLECTION_APPROVAL"
BLOCKED = "BLOCKED"
FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class ExpansionCollectorEvidence:
    target_count: int
    fresh_eligible_count: int
    isolated_database_verified: bool
    request_budget_confirmed: bool
    rate_limit_safety_confirmed: bool
    overlap_and_uniqueness_validation_ready: bool
    backup_and_restore_verified: bool
    production_schedule_unchanged: bool


@dataclass(frozen=True)
class ExpansionCollectorPlan:
    version: str
    status: str
    target_count: int
    current_policy_item_count: int
    proposed_hits: int
    proposed_request_count: int
    minimum_request_spacing_seconds: float
    estimated_minimum_request_span_seconds: float
    fresh_eligible_gap: int
    explicit_approval_required: bool
    api_request_allowed: bool
    database_write_allowed: bool
    production_schedule_change_allowed: bool
    publication_allowed: bool
    reason_codes: tuple[str, ...]
    next_actions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        value["next_actions"] = list(self.next_actions)
        return value


def _invalid() -> ExpansionCollectorPlan:
    return ExpansionCollectorPlan(
        VERSION, FAIL_CLOSED, TARGET_COUNT, 0, HITS, PROPOSED_REQUEST_COUNT,
        0.0, 0.0, TARGET_COUNT, True, False, False, False, False,
        ("EVIDENCE_INVALID",), ("PROVIDE_TYPED_CURRENT_EVIDENCE",),
    )


def assess(evidence: Any) -> ExpansionCollectorPlan:
    if not isinstance(evidence, ExpansionCollectorEvidence):
        return _invalid()
    int_fields = ("target_count", "fresh_eligible_count")
    bool_fields = tuple(
        field for field in ExpansionCollectorEvidence.__dataclass_fields__
        if field not in int_fields
    )
    if (
        any(type(getattr(evidence, field)) is not int for field in int_fields)
        or any(type(getattr(evidence, field)) is not bool for field in bool_fields)
        or evidence.target_count <= 0
        or evidence.fresh_eligible_count < 0
    ):
        return _invalid()

    policy = collection_policy.date_policy()
    evaluated = collection_policy.evaluate_collection_policy(policy)
    expansion_policy = collection_policy.date_expansion_candidate_policy()
    expansion_evaluated = collection_policy.evaluate_collection_policy(expansion_policy)
    proposed_requests = math.ceil(evidence.target_count / HITS)
    reasons: set[str] = set()
    if evidence.target_count != TARGET_COUNT:
        reasons.add("TARGET_STAGE_INVALID")
    if not evaluated.valid or not evaluated.production_collection_eligible:
        reasons.add("CURRENT_DATE_POLICY_INVALID")
    if evaluated.candidate_total_items != 100 or evaluated.request_count != 2:
        reasons.add("CURRENT_DATE_POLICY_BASELINE_CHANGED")
    if proposed_requests != PROPOSED_REQUEST_COUNT:
        reasons.add("PROPOSED_REQUEST_COUNT_INVALID")
    if (
        not expansion_evaluated.valid
        or expansion_evaluated.request_count != PROPOSED_REQUEST_COUNT
        or expansion_evaluated.candidate_total_items != TARGET_COUNT
        or expansion_policy.enabled is not False
        or expansion_policy.publication_use_allowed is not False
    ):
        reasons.add("ISOLATED_EXPANSION_POLICY_INVALID")

    checks = {
        "ISOLATED_DATABASE_UNVERIFIED": evidence.isolated_database_verified,
        "EXPANDED_REQUEST_BUDGET_UNCONFIRMED": evidence.request_budget_confirmed,
        "RATE_LIMIT_SAFETY_UNCONFIRMED": evidence.rate_limit_safety_confirmed,
        "OVERLAP_UNIQUENESS_VALIDATION_NOT_READY": evidence.overlap_and_uniqueness_validation_ready,
        "BACKUP_RESTORE_UNVERIFIED": evidence.backup_and_restore_verified,
        "PRODUCTION_SCHEDULE_CHANGE_DETECTED": evidence.production_schedule_unchanged,
    }
    reasons.update(reason for reason, passed in checks.items() if passed is not True)

    actions = []
    if not evidence.isolated_database_verified or not evidence.backup_and_restore_verified:
        actions.append("PREPARE_DISPOSABLE_DATABASE_COPY_AND_RESTORE_CHECK")
    if not evidence.request_budget_confirmed or "ISOLATED_EXPANSION_POLICY_INVALID" in reasons:
        actions.append("REVIEW_SIX_REQUEST_ISOLATED_DATE_COLLECTION_BUDGET")
    if not evidence.rate_limit_safety_confirmed:
        actions.append("VERIFY_STOP_ON_ERROR_ZERO_RETRY_AND_REQUEST_SPACING")
    if not evidence.overlap_and_uniqueness_validation_ready:
        actions.append("ADD_EXACT_PAGE_OVERLAP_AND_DUPLICATE_VALIDATION")
    if not evidence.production_schedule_unchanged:
        actions.append("RESTORE_EXISTING_TWO_REQUEST_DAILY_SCHEDULE")

    ready = not reasons
    spacing = float(policy.minimum_delay_between_requests_seconds)
    return ExpansionCollectorPlan(
        VERSION, READY if ready else BLOCKED, evidence.target_count,
        evaluated.candidate_total_items, HITS, proposed_requests, spacing,
        spacing * max(0, proposed_requests - 1),
        max(0, evidence.target_count - evidence.fresh_eligible_count),
        True, False, False, False, False, tuple(sorted(reasons)),
        tuple(dict.fromkeys(actions)),
    )


def current_evidence() -> ExpansionCollectorEvidence:
    return ExpansionCollectorEvidence(
        target_count=TARGET_COUNT,
        fresh_eligible_count=108,
        isolated_database_verified=True,
        request_budget_confirmed=True,
        rate_limit_safety_confirmed=True,
        overlap_and_uniqueness_validation_ready=True,
        backup_and_restore_verified=True,
        production_schedule_unchanged=True,
    )


def main() -> int:
    result = assess(current_evidence())
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {READY, BLOCKED} else 2


if __name__ == "__main__":
    raise SystemExit(main())
