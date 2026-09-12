"""Offline scenario rehearsal for the pending Lifecycle and Sort response."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
from typing import Any

import official_response_intake as intake
from official_blocker_policy import LIFECYCLE_BLOCKER, SORT_BLOCKER


VERSION = "0.1"
PASS = "OFFICIAL_RESPONSE_REHEARSAL_PASS"
BLOCKED = "OFFICIAL_RESPONSE_REHEARSAL_BLOCKED"
CHECKS_REQUIRED = 7
STAMP = "2026-09-12T00:00:00+09:00"


@dataclass(frozen=True)
class OfficialResponseRehearsalResult:
    version: str
    status: str
    checks_passed: int
    checks_required: int
    complete_lifecycle_candidate_verified: bool
    complete_sort_candidate_verified: bool
    partial_response_blocked: bool
    ambiguous_response_review_required: bool
    contradictory_response_review_required: bool
    unsafe_raw_input_blocked: bool
    no_gate_mutation_verified: bool
    gate_unlock_allowed: bool
    production_activation_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _response(
    blocker: str,
    *,
    answered: dict[str, str],
    confirmations: tuple[str, ...] = (),
    ambiguity: tuple[str, ...] = (),
) -> intake.SanitizedOfficialResponse:
    questions = (
        intake.LIFECYCLE_QUESTION_IDS
        if blocker == LIFECYCLE_BLOCKER
        else intake.SORT_QUESTION_IDS
    )
    return intake.SanitizedOfficialResponse(
        intake.INTAKE_VERSION,
        "0.1",
        STAMP,
        intake.DIRECT_SUPPORT_CONFIRMATION,
        "DMM_AFFILIATE_SUPPORT",
        blocker,
        answered,
        tuple(question for question in questions if question not in answered),
        confirmations,
        (),
        ambiguity,
        "followup-response-rehearsal",
        {},
    )


def _complete(blocker: str) -> intake.OfficialResponseIntakeResult:
    questions = (
        intake.LIFECYCLE_QUESTION_IDS
        if blocker == LIFECYCLE_BLOCKER
        else intake.SORT_QUESTION_IDS
    )
    return intake.classify_official_response(
        _response(
            blocker,
            answered={question: intake.RESOLVED for question in questions},
            confirmations=questions,
        )
    )


def run_rehearsal() -> OfficialResponseRehearsalResult:
    try:
        lifecycle = _complete(LIFECYCLE_BLOCKER)
        sort = _complete(SORT_BLOCKER)
        lifecycle_ok = (
            lifecycle.resolution_status == intake.RESOLVED
            and lifecycle.gate_unlock_candidate is True
            and lifecycle.manual_review_required is True
        )
        sort_ok = (
            sort.resolution_status == intake.RESOLVED
            and sort.gate_unlock_candidate is True
            and sort.manual_review_required is True
        )

        first = intake.LIFECYCLE_QUESTION_IDS[0]
        partial = intake.classify_official_response(
            _response(
                LIFECYCLE_BLOCKER,
                answered={first: intake.RESOLVED},
                confirmations=(first,),
            )
        )
        partial_ok = (
            partial.resolution_status == intake.PARTIALLY_RESOLVED
            and partial.gate_unlock_candidate is False
        )

        ambiguous = intake.classify_official_response(
            _response(
                LIFECYCLE_BLOCKER,
                answered={first: intake.PARTIALLY_RESOLVED},
                ambiguity=(first,),
            )
        )
        ambiguous_ok = (
            ambiguous.gate_unlock_candidate is False
            and ambiguous.manual_review_required is True
            and "AMBIGUOUS_RESPONSE" in ambiguous.safe_reason_codes
        )

        contradictory_value = replace(
            _response(
                SORT_BLOCKER,
                answered={intake.SORT_QUESTION_IDS[0]: intake.RESOLVED},
                confirmations=(intake.SORT_QUESTION_IDS[0],),
            ),
            explicit_denials=(intake.SORT_QUESTION_IDS[0],),
        )
        contradictory = intake.classify_official_response(contradictory_value)
        contradictory_ok = (
            contradictory.resolution_status == intake.CONTRADICTORY
            and contradictory.gate_unlock_candidate is False
            and contradictory.manual_review_required is True
        )

        unsafe = intake.classify_official_response({"raw_email_body": "fixture"})
        unsafe_ok = unsafe.resolution_status == intake.FAIL_CLOSED
        no_mutation = not any(
            name.startswith("set_") or name.startswith("update_")
            for name in dir(intake)
        )
        manual_boundary = (
            lifecycle.gate_unlock_candidate
            and sort.gate_unlock_candidate
            and lifecycle.manual_review_required
            and sort.manual_review_required
        )
        checks = (
            lifecycle_ok, sort_ok, partial_ok, ambiguous_ok,
            contradictory_ok, unsafe_ok, no_mutation and manual_boundary,
        )
        passed = sum(checks)
        ready = passed == CHECKS_REQUIRED
        return OfficialResponseRehearsalResult(
            VERSION, PASS if ready else BLOCKED, passed, CHECKS_REQUIRED,
            lifecycle_ok, sort_ok, partial_ok, ambiguous_ok, contradictory_ok,
            unsafe_ok, no_mutation, False, False,
            (
                "RESPONSE_SCENARIOS_VERIFIED",
                "COMPLETE_RESPONSE_STILL_REQUIRES_SEPARATE_GATE_REVIEW",
            ) if ready else ("RESPONSE_REHEARSAL_INCOMPLETE",),
        )
    except Exception:
        return OfficialResponseRehearsalResult(
            VERSION, BLOCKED, 0, CHECKS_REQUIRED,
            False, False, False, False, False, False, False, False, False,
            ("RESPONSE_REHEARSAL_ERROR",),
        )


def main() -> int:
    result = run_rehearsal()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
