"""Atomic fail-closed handoff for the Lifecycle and Sort responses."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

import official_blocker_policy as policy
import revenue_mvp_official_response_handoff as single


VERSION = "0.1"
READY_FOR_COMBINED_REVIEW = "READY_FOR_COMBINED_SEPARATE_GATE_REVIEW"
RESPONSE_INCOMPLETE = "RESPONSE_INCOMPLETE"
FAIL_CLOSED = "FAIL_CLOSED"
REQUIRED_BLOCKERS = frozenset({policy.LIFECYCLE_BLOCKER, policy.SORT_BLOCKER})


@dataclass(frozen=True)
class OfficialResponseBatchHandoff:
    version: str
    status: str
    lifecycle_status: str
    sort_status: str
    lifecycle_resolved_question_count: int
    sort_resolved_question_count: int
    total_unresolved_question_count: int
    total_contradictory_question_count: int
    combined_gate_review_candidate: bool
    gate_mutation_allowed: bool
    production_activation_allowed: bool
    next_action: str
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(value["reason_codes"])
        return value


def _failed(reason: str) -> OfficialResponseBatchHandoff:
    return OfficialResponseBatchHandoff(
        VERSION, FAIL_CLOSED, "UNKNOWN", "UNKNOWN", 0, 0, 0, 0,
        False, False, False, "CORRECT_SANITIZED_RESPONSE_BATCH", (reason,),
    )


def handoff_batch(value: Any) -> OfficialResponseBatchHandoff:
    """Require exactly one Lifecycle and one Sort response; never mutate Gates."""
    try:
        if type(value) is not list or len(value) != 2:
            return _failed("EXACTLY_TWO_SANITIZED_RESPONSES_REQUIRED")
        results = [single.handoff(entry) for entry in value]
        if any(result.status == single.FAIL_CLOSED for result in results):
            return _failed("SANITIZED_RESPONSE_BATCH_MEMBER_INVALID")
        by_blocker = {result.affected_blocker: result for result in results}
        if set(by_blocker) != REQUIRED_BLOCKERS or len(by_blocker) != 2:
            return _failed("LIFECYCLE_AND_SORT_RESPONSES_REQUIRED")
        lifecycle = by_blocker[policy.LIFECYCLE_BLOCKER]
        sort = by_blocker[policy.SORT_BLOCKER]
        ready = all(
            result.status == single.READY_FOR_REVIEW
            and result.gate_unlock_candidate is True
            and result.manual_review_required is True
            and result.gate_mutation_allowed is False
            and result.production_activation_allowed is False
            for result in (lifecycle, sort)
        )
        unresolved = sum(
            result.unresolved_question_count for result in (lifecycle, sort)
        )
        contradictory = sum(
            result.contradictory_question_count for result in (lifecycle, sort)
        )
        return OfficialResponseBatchHandoff(
            VERSION,
            READY_FOR_COMBINED_REVIEW if ready else RESPONSE_INCOMPLETE,
            lifecycle.resolution_status,
            sort.resolution_status,
            lifecycle.resolved_question_count,
            sort.resolved_question_count,
            unresolved,
            contradictory,
            ready,
            False,
            False,
            (
                "PERFORM_SEPARATE_LIFECYCLE_AND_SORT_GATE_REVIEWS"
                if ready else "RESOLVE_INCOMPLETE_RESPONSE_TOPICS"
            ),
            (
                "BOTH_RESPONSE_SCOPES_COMPLETE_SEPARATE_REVIEW_REQUIRED",
            ) if ready else ("ONE_OR_MORE_RESPONSE_SCOPES_INCOMPLETE",),
        )
    except Exception:
        return _failed("SANITIZED_RESPONSE_BATCH_INTERNAL_ERROR")


def main() -> int:
    result = _failed("NO_RESPONSE_INPUT_ACCEPTED_ON_STANDARD_INPUT")
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
