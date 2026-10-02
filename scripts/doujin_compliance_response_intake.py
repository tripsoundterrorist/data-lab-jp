"""Fail-closed intake for sanitized doujin compliance answers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import re
from typing import Any, Mapping

from doujin_compliance_handoff import QUESTION_IDS


VERSION = "0.1"
COMPLETE = "READY_FOR_SEPARATE_COMPLIANCE_DECISION"
PARTIAL = "PARTIAL_OFFICIAL_RESPONSE"
CONTRADICTORY = "CONTRADICTORY_OFFICIAL_RESPONSE"
FAIL_CLOSED = "FAIL_CLOSED"

DIRECT_SUPPORT = "DIRECT_SUPPORT_CONFIRMATION"
OFFICIAL_DOCS = "OFFICIAL_DOCUMENTATION"
EVIDENCE = frozenset({
    (DIRECT_SUPPORT, "DMM_AFFILIATE_SUPPORT"),
    (OFFICIAL_DOCS, "DMM_OFFICIAL_DOCUMENTATION"),
})

ALLOW = "RESOLVED_ALLOW"
DENY = "RESOLVED_DENY"
REQUIREMENTS = "RESOLVED_REQUIREMENTS"
UNRESOLVED = "UNRESOLVED"
CONFLICT = "CONTRADICTORY"
STATES = frozenset({ALLOW, DENY, REQUIREMENTS, UNRESOLVED, CONFLICT})
RESOLVED_STATES = frozenset({ALLOW, DENY, REQUIREMENTS})

_UNSAFE = re.compile(
    r"(?i)(?:https?://|file://|[a-z]:[\\/]|\\\\|\b[^\s@]+@[^\s@]+\.[^\s@]+\b|"
    r"(?:api|affiliate)[_-]?id\s*[:=]|(?:password|secret|token)\s*[:=])"
)


@dataclass(frozen=True)
class SanitizedDoujinComplianceResponse:
    version: str
    received_at: str
    source_type: str
    source_authority: str
    safe_reference: str
    question_states: Mapping[str, str]
    explicitly_answered_question_ids: tuple[str, ...]


@dataclass(frozen=True)
class DoujinComplianceIntakeResult:
    version: str
    status: str
    resolved_question_ids: tuple[str, ...]
    unresolved_question_ids: tuple[str, ...]
    contradictory_question_ids: tuple[str, ...]
    separate_compliance_decision_candidate: bool
    compliance_approved: bool
    gate_change_allowed: bool
    publication_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in (
            "resolved_question_ids", "unresolved_question_ids",
            "contradictory_question_ids", "reason_codes",
        ):
            value[key] = list(value[key])
        return value


def _result(
    status: str,
    *,
    resolved: tuple[str, ...] = (),
    unresolved: tuple[str, ...] = (),
    contradictory: tuple[str, ...] = (),
    candidate: bool = False,
    reasons: tuple[str, ...],
) -> DoujinComplianceIntakeResult:
    return DoujinComplianceIntakeResult(
        VERSION, status, resolved, unresolved, contradictory, candidate,
        False, False, False, reasons,
    )


def _timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized).tzinfo is not None
    except ValueError:
        return False


def classify(value: Any) -> DoujinComplianceIntakeResult:
    if not isinstance(value, SanitizedDoujinComplianceResponse):
        return _result(FAIL_CLOSED, reasons=("MALFORMED_INPUT",))
    try:
        if (
            value.version != VERSION
            or not _timestamp(value.received_at)
            or (value.source_type, value.source_authority) not in EVIDENCE
            or not isinstance(value.safe_reference, str)
            or not value.safe_reference.strip()
            or _UNSAFE.search(value.safe_reference)
        ):
            return _result(FAIL_CLOSED, reasons=("INVALID_OR_UNSAFE_EVIDENCE",))
        states = dict(value.question_states)
        known = set(QUESTION_IDS)
        if set(states) != known or any(state not in STATES for state in states.values()):
            return _result(FAIL_CLOSED, reasons=("QUESTION_SET_INVALID",))
        explicit = set(value.explicitly_answered_question_ids)
        if len(explicit) != len(value.explicitly_answered_question_ids) or not explicit <= known:
            return _result(FAIL_CLOSED, reasons=("EXPLICIT_ANSWER_SET_INVALID",))
        inferred = {
            question for question, state in states.items()
            if state in RESOLVED_STATES and question not in explicit
        }
        if inferred:
            return _result(FAIL_CLOSED, reasons=("INFERRED_RESOLUTION_FORBIDDEN",))
        resolved = tuple(q for q in QUESTION_IDS if states[q] in RESOLVED_STATES)
        contradictory = tuple(q for q in QUESTION_IDS if states[q] == CONFLICT)
        unresolved = tuple(q for q in QUESTION_IDS if states[q] == UNRESOLVED)
        if contradictory:
            return _result(
                CONTRADICTORY, resolved=resolved, unresolved=unresolved,
                contradictory=contradictory,
                reasons=("CONTRADICTORY_RESPONSE", "SEPARATE_REVIEW_REQUIRED"),
            )
        if unresolved:
            return _result(
                PARTIAL, resolved=resolved, unresolved=unresolved,
                reasons=("QUESTIONS_UNRESOLVED", "SEPARATE_REVIEW_REQUIRED"),
            )
        return _result(
            COMPLETE, resolved=resolved, candidate=True,
            reasons=("ALL_QUESTIONS_EXPLICITLY_RESOLVED", "SEPARATE_REVIEW_REQUIRED"),
        )
    except Exception:
        return _result(FAIL_CLOSED, reasons=("MALFORMED_INPUT",))
