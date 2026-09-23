"""Pure, bounded intake for sanitized preconnection Q4/Q5 observations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from revenue_mvp_preconnection_followup_status import QUESTION_IDS


VERSION = "0.1"
BLOCKED = "BLOCKED"
REVIEW_REQUIRED = "SEPARATE_COMPLIANCE_REVIEW_REQUIRED"
YES = "YES"
NO = "NO"
UNSPECIFIED = "UNSPECIFIED"
AMBIGUOUS = "AMBIGUOUS"
CONTRADICTORY = "CONTRADICTORY"

_STATES = frozenset({YES, NO, UNSPECIFIED, AMBIGUOUS, CONTRADICTORY})
_SOURCES = frozenset({
    ("DIRECT_SUPPORT_CONFIRMATION", "DMM_AFFILIATE_SUPPORT"),
    ("OFFICIAL_DOCUMENTATION", "DMM_OFFICIAL_DOCUMENTATION"),
})
_FIELDS = frozenset({"intake_version", "source_type", "source_authority", "question_states"})
_QUESTIONS = frozenset(QUESTION_IDS)


@dataclass(frozen=True)
class PreconnectionOfficialResponseIntake:
    intake_version: str
    status: str
    live_single_request_permission: str
    user_agent_requirement: str
    live_connection_allowed: bool
    gate_unlock_allowed: bool
    compliance_review_required: bool
    explicit_connection_approval_required: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["reason_codes"] = list(self.reason_codes)
        return result


def _result(reason: str, q4: str = UNSPECIFIED, q5: str = UNSPECIFIED,
            status: str = BLOCKED) -> PreconnectionOfficialResponseIntake:
    return PreconnectionOfficialResponseIntake(
        VERSION, status, q4, q5, False, False, True, True, (reason,),
    )


def assess_preconnection_official_response(value: Any) -> PreconnectionOfficialResponseIntake:
    """Classify only two enumerated answers; never grant a connection or Gate."""
    try:
        if type(value) is not dict:
            return _result("MALFORMED_INPUT")
        keys = tuple(value)
        if any(type(key) is not str for key in keys) or frozenset(keys) != _FIELDS:
            return _result("UNKNOWN_OR_MISSING_FIELD")
        if type(value["intake_version"]) is not str or value["intake_version"] != VERSION:
            return _result("INVALID_VERSION")
        source_type = value["source_type"]
        source_authority = value["source_authority"]
        if type(source_type) is not str or type(source_authority) is not str:
            return _result("OFFICIAL_SOURCE_REQUIRED")
        if (source_type, source_authority) not in _SOURCES:
            return _result("OFFICIAL_SOURCE_REQUIRED")
        states = value["question_states"]
        if type(states) is not dict:
            return _result("INVALID_QUESTION_STATES")
        question_keys = tuple(states)
        if any(type(key) is not str for key in question_keys) or frozenset(question_keys) != _QUESTIONS:
            return _result("UNKNOWN_OR_MISSING_QUESTION")
        q4 = states[QUESTION_IDS[0]]
        q5 = states[QUESTION_IDS[1]]
        if type(q4) is not str or type(q5) is not str or q4 not in _STATES or q5 not in _STATES:
            return _result("INVALID_ANSWER_STATE")
        if q4 not in (YES, NO) or q5 not in (YES, NO):
            return _result("ANSWER_UNRESOLVED", q4, q5)
        return _result("SEPARATE_REVIEW_AND_APPROVAL_REQUIRED", q4, q5, REVIEW_REQUIRED)
    except Exception:
        return _result("MALFORMED_INPUT")


__all__ = [
    "AMBIGUOUS", "BLOCKED", "CONTRADICTORY", "NO", "PreconnectionOfficialResponseIntake",
    "REVIEW_REQUIRED", "UNSPECIFIED", "VERSION", "YES",
    "assess_preconnection_official_response",
]
