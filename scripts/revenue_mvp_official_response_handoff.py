"""Strict local handoff from sanitized JSON to official-response intake."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Mapping

import official_response_intake as intake


VERSION = "0.1"
READY_FOR_REVIEW = "READY_FOR_SEPARATE_GATE_REVIEW"
RESPONSE_INCOMPLETE = "RESPONSE_INCOMPLETE"
FAIL_CLOSED = "FAIL_CLOSED"
EXACT_KEYS = frozenset({
    "intake_version", "registry_version", "received_at", "source_type",
    "source_authority", "referenced_blocker", "answered_questions",
    "unanswered_questions", "explicit_confirmations", "explicit_denials",
    "ambiguity_flags", "safe_reference", "prior_question_statuses",
})


@dataclass(frozen=True)
class OfficialResponseHandoff:
    version: str
    status: str
    affected_blocker: str | None
    resolution_status: str
    gate_unlock_candidate: bool
    manual_review_required: bool
    resolved_question_count: int
    unresolved_question_count: int
    contradictory_question_count: int
    production_activation_allowed: bool
    gate_mutation_allowed: bool
    next_action: str
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(value["reason_codes"])
        return value


def _strict_response(value: Any) -> intake.SanitizedOfficialResponse:
    if not isinstance(value, Mapping) or set(value) != EXACT_KEYS:
        raise ValueError("schema mismatch")
    unsafe_probe = intake.classify_official_response(value)
    if "UNSAFE_INPUT" in unsafe_probe.safe_reason_codes:
        raise ValueError("unsafe input")
    scalar_keys = (
        "intake_version", "registry_version", "received_at", "source_type",
        "source_authority", "referenced_blocker",
    )
    if not all(type(value[key]) is str for key in scalar_keys):
        raise ValueError("invalid scalar")
    if value["safe_reference"] is not None and type(value["safe_reference"]) is not str:
        raise ValueError("invalid safe reference")
    mapping_keys = ("answered_questions", "prior_question_statuses")
    if not all(
        isinstance(value[key], Mapping)
        and all(type(k) is str and type(v) is str for k, v in value[key].items())
        for key in mapping_keys
    ):
        raise ValueError("invalid question mapping")
    sequence_keys = (
        "unanswered_questions", "explicit_confirmations", "explicit_denials",
        "ambiguity_flags",
    )
    if not all(
        type(value[key]) is list and all(type(entry) is str for entry in value[key])
        for key in sequence_keys
    ):
        raise ValueError("invalid question sequence")
    return intake.SanitizedOfficialResponse(
        value["intake_version"], value["registry_version"], value["received_at"],
        value["source_type"], value["source_authority"],
        value["referenced_blocker"], dict(value["answered_questions"]),
        tuple(value["unanswered_questions"]),
        tuple(value["explicit_confirmations"]), tuple(value["explicit_denials"]),
        tuple(value["ambiguity_flags"]), value["safe_reference"],
        dict(value["prior_question_statuses"]),
    )


def handoff(value: Any) -> OfficialResponseHandoff:
    """Return only bounded counts and statuses; never echo supplied content."""
    try:
        result = intake.classify_official_response(_strict_response(value))
        if result.resolution_status == intake.RESOLVED and result.gate_unlock_candidate:
            status = READY_FOR_REVIEW
            next_action = "PERFORM_SEPARATE_LIFECYCLE_OR_SORT_GATE_REVIEW"
        elif result.resolution_status in {
            intake.PARTIALLY_RESOLVED, intake.UNRESOLVED, intake.CONTRADICTORY,
        }:
            status = RESPONSE_INCOMPLETE
            next_action = "REVIEW_UNRESOLVED_OR_CONTRADICTORY_QUESTIONS"
        else:
            status = FAIL_CLOSED
            next_action = "CORRECT_SANITIZED_RESPONSE_INPUT"
        return OfficialResponseHandoff(
            VERSION, status, result.affected_blocker, result.resolution_status,
            result.gate_unlock_candidate, result.manual_review_required,
            len(result.resolved_question_ids), len(result.unresolved_question_ids),
            len(result.contradictory_question_ids), False, False, next_action,
            result.safe_reason_codes,
        )
    except Exception:
        return OfficialResponseHandoff(
            VERSION, FAIL_CLOSED, None, intake.FAIL_CLOSED, False, True,
            0, 0, 0, False, False, "CORRECT_SANITIZED_RESPONSE_INPUT",
            ("SANITIZED_RESPONSE_HANDOFF_INVALID",),
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Classify one local sanitized official-response JSON file."
    )
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        value = json.loads(args.input.read_text(encoding="utf-8"))
    except Exception:
        value = None
    result = handoff(value)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {READY_FOR_REVIEW, RESPONSE_INCOMPLETE} else 2


if __name__ == "__main__":
    raise SystemExit(main())
