"""Read-only Gate review packet for complete Lifecycle and Sort responses."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

import revenue_mvp_lifecycle_condition_evidence as lifecycle_evidence
import revenue_mvp_official_response_batch_handoff as batch_handoff
import revenue_mvp_sort_condition_evidence as sort_evidence


VERSION = "0.1"
READY_FOR_MANUAL_REVIEW = "READY_FOR_MANUAL_GATE_UPDATE_REVIEW"
BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class OfficialGateReviewPacket:
    version: str
    status: str
    lifecycle_response_complete: bool
    sort_response_complete: bool
    lifecycle_implementation_evidence_ready: bool
    sort_implementation_evidence_ready: bool
    lifecycle_gate_pass_candidate: bool
    semantics_gate_pass_candidate: bool
    manual_gate_review_required: bool
    registry_mutation_allowed: bool
    publication_gate_unlock_allowed: bool
    production_activation_allowed: bool
    next_action: str
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(value["reason_codes"])
        return value


def build_review_packet(
    response_batch: Any,
    lifecycle: Any,
    sort: Any,
) -> OfficialGateReviewPacket:
    """Assess a candidate only; never update the blocker registry or any Gate."""
    try:
        response_ready = (
            response_batch.version == batch_handoff.VERSION
            and response_batch.status == batch_handoff.READY_FOR_COMBINED_REVIEW
            and response_batch.lifecycle_status == "RESOLVED"
            and response_batch.sort_status == "RESOLVED"
            and response_batch.lifecycle_resolved_question_count == 9
            and response_batch.sort_resolved_question_count == 8
            and response_batch.total_unresolved_question_count == 0
            and response_batch.total_contradictory_question_count == 0
            and response_batch.combined_gate_review_candidate is True
            and response_batch.gate_mutation_allowed is False
            and response_batch.production_activation_allowed is False
        )
        lifecycle_ready = (
            lifecycle.version == lifecycle_evidence.VERSION
            and lifecycle.status == lifecycle_evidence.EVIDENCE_READY
            and lifecycle.implementation_evidence_candidate is True
            and lifecycle.official_semantics_resolved is False
            and lifecycle.publication_gate_unlock_allowed is False
            and lifecycle.checks_passed == lifecycle.checks_required
        )
        sort_ready = (
            sort.version == sort_evidence.VERSION
            and sort.status == sort_evidence.EVIDENCE_READY
            and sort.implementation_evidence_candidate is True
            and sort.official_semantics_resolved is False
            and sort.publication_gate_unlock_allowed is False
            and sort.checks_passed == sort.checks_required
        )
        ready = response_ready and lifecycle_ready and sort_ready
        return OfficialGateReviewPacket(
            VERSION,
            READY_FOR_MANUAL_REVIEW if ready else BLOCKED,
            response_ready,
            response_ready,
            lifecycle_ready,
            sort_ready,
            ready,
            ready,
            ready,
            False,
            False,
            False,
            (
                "REVIEW_PROPOSED_BLOCKER_RECORDS_IN_SEPARATE_COMMIT"
                if ready else "RECONCILE_RESPONSE_AND_IMPLEMENTATION_EVIDENCE"
            ),
            (
                "OFFICIAL_RESPONSE_AND_IMPLEMENTATION_EVIDENCE_ALIGNED",
                "GATE_UPDATE_REQUIRES_SEPARATE_EXPLICIT_APPROVAL",
            ) if ready else ("OFFICIAL_GATE_REVIEW_INPUT_INCOMPLETE",),
        )
    except Exception:
        return OfficialGateReviewPacket(
            VERSION, BLOCKED, False, False, False, False, False, False,
            True, False, False, False,
            "RECONCILE_RESPONSE_AND_IMPLEMENTATION_EVIDENCE",
            ("OFFICIAL_GATE_REVIEW_INPUT_INVALID",),
        )


def main() -> int:
    result = build_review_packet(
        None,
        lifecycle_evidence.assess_lifecycle_condition_evidence(),
        sort_evidence.assess_sort_condition_evidence(),
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY_FOR_MANUAL_REVIEW else 2


if __name__ == "__main__":
    raise SystemExit(main())
