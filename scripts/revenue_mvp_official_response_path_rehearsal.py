"""Offline end-to-end rehearsal of the official-response review path."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

import official_blocker_policy as policy
import official_response_intake as intake
import revenue_mvp_lifecycle_condition_evidence as lifecycle_evidence
import revenue_mvp_official_gate_review_packet as gate_review
import revenue_mvp_official_response_batch_handoff as batch_handoff
import revenue_mvp_sort_condition_evidence as sort_evidence


VERSION = "0.1"
PASS = "OFFICIAL_RESPONSE_PATH_REHEARSAL_PASS"
BLOCKED = "OFFICIAL_RESPONSE_PATH_REHEARSAL_BLOCKED"
CHECKS_REQUIRED = 6


@dataclass(frozen=True)
class OfficialResponsePathRehearsal:
    version: str
    status: str
    checks_passed: int
    checks_required: int
    combined_response_handoff_verified: bool
    lifecycle_evidence_verified: bool
    sort_evidence_verified: bool
    manual_gate_review_boundary_verified: bool
    partial_response_stop_verified: bool
    no_mutation_boundary_verified: bool
    network_request_performed: bool
    production_write_performed: bool
    gate_mutation_allowed: bool
    production_activation_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(value["reason_codes"])
        return value


def _response(blocker: str) -> dict[str, Any]:
    questions = (
        intake.LIFECYCLE_QUESTION_IDS
        if blocker == policy.LIFECYCLE_BLOCKER else intake.SORT_QUESTION_IDS
    )
    return {
        "intake_version": intake.INTAKE_VERSION,
        "registry_version": policy.POLICY_VERSION,
        "received_at": "2026-09-12T12:00:00+09:00",
        "source_type": policy.DIRECT_SUPPORT_CONFIRMATION,
        "source_authority": "DMM_AFFILIATE_SUPPORT",
        "referenced_blocker": blocker,
        "answered_questions": {question: intake.RESOLVED for question in questions},
        "unanswered_questions": [],
        "explicit_confirmations": list(questions),
        "explicit_denials": [],
        "ambiguity_flags": [],
        "safe_reference": "offline-rehearsal-fixture",
        "prior_question_statuses": {},
    }


def run_rehearsal() -> OfficialResponsePathRehearsal:
    try:
        complete = [
            _response(policy.LIFECYCLE_BLOCKER),
            _response(policy.SORT_BLOCKER),
        ]
        batch = batch_handoff.handoff_batch(complete)
        lifecycle = lifecycle_evidence.assess_lifecycle_condition_evidence()
        sort = sort_evidence.assess_sort_condition_evidence()
        review = gate_review.build_review_packet(batch, lifecycle, sort)

        partial = [dict(complete[0]), dict(complete[1])]
        partial[1]["answered_questions"] = dict(partial[1]["answered_questions"])
        partial[1]["explicit_confirmations"] = list(
            partial[1]["explicit_confirmations"]
        )
        question = intake.SORT_QUESTION_IDS[-1]
        partial[1]["answered_questions"].pop(question)
        partial[1]["explicit_confirmations"].remove(question)
        partial[1]["unanswered_questions"] = [question]
        partial_batch = batch_handoff.handoff_batch(partial)
        partial_review = gate_review.build_review_packet(
            partial_batch, lifecycle, sort
        )

        checks = (
            batch.status == batch_handoff.READY_FOR_COMBINED_REVIEW,
            lifecycle.status == lifecycle_evidence.EVIDENCE_READY
            and lifecycle.checks_passed == lifecycle.checks_required,
            sort.status == sort_evidence.EVIDENCE_READY
            and sort.checks_passed == sort.checks_required,
            review.status == gate_review.READY_FOR_MANUAL_REVIEW
            and review.manual_gate_review_required is True,
            partial_batch.status == batch_handoff.RESPONSE_INCOMPLETE
            and partial_review.status == gate_review.BLOCKED,
            all(
                value is False
                for value in (
                    batch.gate_mutation_allowed,
                    batch.production_activation_allowed,
                    review.registry_mutation_allowed,
                    review.publication_gate_unlock_allowed,
                    review.production_activation_allowed,
                    partial_review.registry_mutation_allowed,
                    partial_review.production_activation_allowed,
                )
            ),
        )
        passed = sum(check is True for check in checks)
        ready = passed == CHECKS_REQUIRED
        return OfficialResponsePathRehearsal(
            VERSION, PASS if ready else BLOCKED, passed, CHECKS_REQUIRED,
            checks[0], checks[1], checks[2], checks[3], checks[4], checks[5],
            False, False, False, False,
            (
                "OFFICIAL_RESPONSE_REVIEW_PATH_VERIFIED_OFFLINE",
                "REAL_GATE_UPDATE_REQUIRES_FRESH_RESPONSE_AND_EXPLICIT_APPROVAL",
            ) if ready else ("OFFICIAL_RESPONSE_REVIEW_PATH_INCOMPLETE",),
        )
    except Exception:
        return OfficialResponsePathRehearsal(
            VERSION, BLOCKED, 0, CHECKS_REQUIRED, False, False, False, False,
            False, False, False, False, False, False,
            ("OFFICIAL_RESPONSE_REVIEW_PATH_INTERNAL_ERROR",),
        )


def main() -> int:
    result = run_rehearsal()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
