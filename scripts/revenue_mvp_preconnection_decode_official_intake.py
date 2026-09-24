"""Pure intake for sanitized Q1/Q3 official answer states; no wire decoding."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


VERSION = "0.1"
BLOCKED = "BLOCKED"
REVIEW_REQUIRED = "SEPARATE_COMPLIANCE_REVIEW_REQUIRED"
YES = "YES"
NO = "NO"
UNSPECIFIED = "UNSPECIFIED"
AMBIGUOUS = "AMBIGUOUS"
CONTRADICTORY = "CONTRADICTORY"

QUESTION_IDS = (
    "OUTPUT_JSON_SUCCESS_RESULT_STATUS_NUMERIC_200",
    "SUCCESS_CONTENT_TYPE_JSON_UTF8_INCLUDING_CHARSET_OMISSION",
)
_STATES = frozenset({YES, NO, UNSPECIFIED, AMBIGUOUS, CONTRADICTORY})
_SOURCES = frozenset({
    ("DIRECT_SUPPORT_CONFIRMATION", "DMM_AFFILIATE_SUPPORT"),
    ("OFFICIAL_DOCUMENTATION", "DMM_OFFICIAL_DOCUMENTATION"),
})
_FIELDS = frozenset({"intake_version", "source_type", "source_authority", "question_states"})
_QUESTIONS = frozenset(QUESTION_IDS)


@dataclass(frozen=True)
class PreconnectionDecodeOfficialIntake:
    intake_version: str
    status: str
    q1_numeric_status_answer: str
    q3_json_utf8_answer: str
    live_connection_allowed: bool
    gate_unlock_allowed: bool
    live_decode_profile_approved: bool
    compliance_review_required: bool
    explicit_connection_approval_required: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["reason_codes"] = list(self.reason_codes)
        return result


def _result(reason: str, q1: str = UNSPECIFIED, q3: str = UNSPECIFIED,
            status: str = BLOCKED) -> PreconnectionDecodeOfficialIntake:
    return PreconnectionDecodeOfficialIntake(
        VERSION, status, q1, q3, False, False, False, True, True, (reason,),
    )


def assess_preconnection_decode_official_response(value: Any) -> PreconnectionDecodeOfficialIntake:
    """Classify fixed answer states without granting a live decode profile."""
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
        q1 = states[QUESTION_IDS[0]]
        q3 = states[QUESTION_IDS[1]]
        if type(q1) is not str or type(q3) is not str or q1 not in _STATES or q3 not in _STATES:
            return _result("INVALID_ANSWER_STATE")
        if q1 not in (YES, NO) or q3 not in (YES, NO):
            return _result("ANSWER_UNRESOLVED", q1, q3)
        return _result("SEPARATE_REVIEW_AND_APPROVAL_REQUIRED", q1, q3, REVIEW_REQUIRED)
    except Exception:
        return _result("MALFORMED_INPUT")


__all__ = [
    "AMBIGUOUS", "BLOCKED", "CONTRADICTORY", "NO", "PreconnectionDecodeOfficialIntake",
    "QUESTION_IDS", "REVIEW_REQUIRED", "UNSPECIFIED", "VERSION", "YES",
    "assess_preconnection_decode_official_response",
]
