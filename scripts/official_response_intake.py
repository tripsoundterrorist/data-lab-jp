"""Pure, fail-closed classification of sanitized official responses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Mapping

from official_blocker_policy import (
    BLOCKER_IDS, DIRECT_SUPPORT_CONFIRMATION, LIFECYCLE_BLOCKER,
    OFFICIAL_DOCUMENTATION, POLICY_VERSION as REGISTRY_VERSION,
    SORT_BLOCKER,
)


INTAKE_VERSION = "0.1"
RIGHTS_BLOCKER = "DMM_RIGHTS_USAGE"
ALLOWED_BLOCKERS = frozenset({LIFECYCLE_BLOCKER, SORT_BLOCKER, RIGHTS_BLOCKER})
ALLOWED_SOURCE_TYPES = frozenset({DIRECT_SUPPORT_CONFIRMATION, OFFICIAL_DOCUMENTATION})
ALLOWED_AUTHORITIES = frozenset({"DMM_AFFILIATE_SUPPORT", "DMM_OFFICIAL_DOCUMENTATION"})

RESOLVED = "RESOLVED"
PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
UNRESOLVED = "UNRESOLVED"
CONTRADICTORY = "CONTRADICTORY"
FAIL_CLOSED = "FAIL_CLOSED"
DUPLICATE_CONFIRMATION = "DUPLICATE_CONFIRMATION"
QUESTION_STATES = frozenset({RESOLVED, PARTIALLY_RESOLVED, UNRESOLVED, CONTRADICTORY})

LIFECYCLE_QUESTION_IDS = (
    "CID_ZERO_RESULT_MEANING", "API_VISIBLE_MEANING", "API_INVISIBLE_MEANING",
    "AFFILIATE_URL_PRESENCE_MEANING", "AFFILIATE_URL_ABSENCE_MEANING",
    "PERIODIC_REQUERY_RECOMMENDATION", "NONVISIBLE_PAGE_HANDLING",
    "NONVISIBLE_LINK_HANDLING", "HISTORICAL_METADATA_RETENTION",
)
SORT_QUESTION_IDS = (
    "RANK_SORT_DEFINITION", "REVIEW_SORT_DEFINITION", "RANK_ORDERING_RULE",
    "REVIEW_ORDERING_RULE", "OFFSET_MEANING", "POSITION_MEANING",
    "PUBLIC_POSITION_EXPRESSION", "UPDATE_BEHAVIOR",
)
RANK_REQUIRED = frozenset({"RANK_SORT_DEFINITION", "RANK_ORDERING_RULE"})
REVIEW_REQUIRED = frozenset({"REVIEW_SORT_DEFINITION", "REVIEW_ORDERING_RULE"})
POSITION_REQUIRED = frozenset({"OFFSET_MEANING", "POSITION_MEANING", "PUBLIC_POSITION_EXPRESSION"})

REASON_ORDER = (
    "MALFORMED_INPUT", "UNKNOWN_VERSION", "REGISTRY_VERSION_MISMATCH",
    "UNKNOWN_BLOCKER", "UNKNOWN_SOURCE_TYPE", "UNKNOWN_SOURCE_AUTHORITY",
    "UNKNOWN_QUESTION_ID", "UNKNOWN_QUESTION_STATUS", "UNSAFE_INPUT",
    "INFERRED_STATUS_FORBIDDEN", "AMBIGUOUS_RESPONSE", "CONTRADICTORY_RESPONSE",
    "NO_OFFICIAL_EVIDENCE", "QUESTIONS_UNANSWERED", "PARTIAL_RESPONSE",
    "GATE_CHANGE_REQUIRES_SEPARATE_REVIEW", "RIGHTS_ALREADY_RESOLVED",
)
_UNSAFE_KEY = re.compile(r"(?i)^(?:raw_email|raw_email_body|email_body|sender|sender_email|raw_response|credential|credentials|api_id|affiliate_id|traceback|exception|file_path|absolute_path)$")
_EMAIL = re.compile(r"(?i)\b[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9.-]+\.[a-z]{2,}\b")
_URL = re.compile(r"(?i)\b(?:https?|file)://")
_SECRET = re.compile(r"(?i)(?:api|affiliate)[_-]?id\s*[:=]|(?:password|secret|token)\s*[:=]|bearer\s+[a-z0-9._~-]{6,}")
_PATH = re.compile(r"(?i)(?:(?<![a-z])[a-z]:[\\/]|^\\\\|^/(?!/)|/home/|/users/)")


@dataclass(frozen=True)
class SanitizedOfficialResponse:
    intake_version: str
    registry_version: str
    received_at: str
    source_type: str
    source_authority: str
    referenced_blocker: str
    answered_questions: Mapping[str, str]
    unanswered_questions: tuple[str, ...]
    explicit_confirmations: tuple[str, ...]
    explicit_denials: tuple[str, ...]
    ambiguity_flags: tuple[str, ...]
    safe_reference: str | None
    prior_question_statuses: Mapping[str, str]


@dataclass(frozen=True)
class OfficialResponseIntakeResult:
    intake_version: str
    affected_blocker: str | None
    source_type: str | None
    received_at: str | None
    resolution_status: str
    resolved_question_ids: tuple[str, ...]
    unresolved_question_ids: tuple[str, ...]
    contradictory_question_ids: tuple[str, ...]
    gate_unlock_candidate: bool
    manual_review_required: bool
    safe_reason_codes: tuple[str, ...]
    next_required_questions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "intake_version": self.intake_version,
            "affected_blocker": self.affected_blocker,
            "source_type": self.source_type,
            "received_at": self.received_at,
            "resolution_status": self.resolution_status,
            "resolved_question_ids": list(self.resolved_question_ids),
            "unresolved_question_ids": list(self.unresolved_question_ids),
            "contradictory_question_ids": list(self.contradictory_question_ids),
            "gate_unlock_candidate": self.gate_unlock_candidate,
            "manual_review_required": self.manual_review_required,
            "safe_reason_codes": list(self.safe_reason_codes),
            "next_required_questions": list(self.next_required_questions),
        }


def _timestamp(value: Any) -> bool:
    if not isinstance(value, str): return False
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try: return datetime.fromisoformat(normalized).tzinfo is not None
    except ValueError: return False


def _unsafe(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(not isinstance(key, str) or _UNSAFE_KEY.fullmatch(key) or _unsafe(child) for key, child in value.items())
    if isinstance(value, (list, tuple)):
        return any(_unsafe(child) for child in value)
    return isinstance(value, str) and any(pattern.search(value) for pattern in (_EMAIL, _URL, _SECRET, _PATH))


def _result(value: SanitizedOfficialResponse | None, status: str, reasons: set[str], *, resolved=(), unresolved=(), contradictory=(), unlock=False, manual=False, next_required=()) -> OfficialResponseIntakeResult:
    return OfficialResponseIntakeResult(
        INTAKE_VERSION, value.referenced_blocker if value else None,
        value.source_type if value else None, value.received_at if value else None,
        status, tuple(resolved), tuple(unresolved), tuple(contradictory), unlock,
        manual, tuple(code for code in REASON_ORDER if code in reasons),
        tuple(next_required),
    )


def classify_official_response(value: Any) -> OfficialResponseIntakeResult:
    try:
        if isinstance(value, Mapping):
            if _unsafe(value): return _result(None, FAIL_CLOSED, {"UNSAFE_INPUT"}, manual=True)
            return _result(None, FAIL_CLOSED, {"MALFORMED_INPUT"}, manual=True)
        if not isinstance(value, SanitizedOfficialResponse):
            return _result(None, FAIL_CLOSED, {"MALFORMED_INPUT"}, manual=True)
        reasons: set[str] = set()
        if value.intake_version != INTAKE_VERSION: reasons.add("UNKNOWN_VERSION")
        if value.registry_version != REGISTRY_VERSION: reasons.add("REGISTRY_VERSION_MISMATCH")
        if value.referenced_blocker not in ALLOWED_BLOCKERS: reasons.add("UNKNOWN_BLOCKER")
        if value.source_type not in ALLOWED_SOURCE_TYPES: reasons.update({"UNKNOWN_SOURCE_TYPE", "NO_OFFICIAL_EVIDENCE"})
        if value.source_authority not in ALLOWED_AUTHORITIES: reasons.add("UNKNOWN_SOURCE_AUTHORITY")
        if not _timestamp(value.received_at): reasons.add("MALFORMED_INPUT")
        if _unsafe(value.safe_reference) or _unsafe(value.answered_questions) or _unsafe(value.explicit_confirmations) or _unsafe(value.explicit_denials): reasons.add("UNSAFE_INPUT")
        if reasons:
            return _result(value, FAIL_CLOSED, reasons, manual=True)

        if value.referenced_blocker == RIGHTS_BLOCKER:
            contradictory = tuple(sorted(set(value.ambiguity_flags) | {q for q, state in value.answered_questions.items() if state == CONTRADICTORY}))
            if contradictory:
                return _result(value, CONTRADICTORY, {"CONTRADICTORY_RESPONSE", "RIGHTS_ALREADY_RESOLVED", "GATE_CHANGE_REQUIRES_SEPARATE_REVIEW"}, contradictory=contradictory, manual=True)
            return _result(value, DUPLICATE_CONFIRMATION, {"RIGHTS_ALREADY_RESOLVED", "GATE_CHANGE_REQUIRES_SEPARATE_REVIEW"}, manual=False)

        ordered_questions = LIFECYCLE_QUESTION_IDS if value.referenced_blocker == LIFECYCLE_BLOCKER else SORT_QUESTION_IDS
        known = set(ordered_questions)
        supplied = set(value.answered_questions) | set(value.unanswered_questions) | set(value.ambiguity_flags) | set(value.prior_question_statuses)
        if supplied - known:
            return _result(value, FAIL_CLOSED, {"UNKNOWN_QUESTION_ID"}, manual=True)
        if any(state not in QUESTION_STATES for state in value.answered_questions.values()) or any(state not in QUESTION_STATES for state in value.prior_question_statuses.values()):
            return _result(value, FAIL_CLOSED, {"UNKNOWN_QUESTION_STATUS"}, manual=True)
        explicit = set(value.explicit_confirmations) | set(value.explicit_denials)
        inferred = {q for q, state in value.answered_questions.items() if state == RESOLVED and q not in explicit}
        if inferred:
            return _result(value, FAIL_CLOSED, {"INFERRED_STATUS_FORBIDDEN"}, unresolved=tuple(q for q in ordered_questions if q not in explicit), manual=True, next_required=tuple(q for q in ordered_questions if q not in explicit))
        contradictory_set = {
            q for q, state in value.answered_questions.items()
            if state == CONTRADICTORY
        }
        contradictory_set |= set(value.explicit_confirmations) & set(value.explicit_denials)
        contradictory_set |= {
            q for q in value.answered_questions
            if value.prior_question_statuses.get(q) == CONTRADICTORY
        }
        ambiguous = set(value.ambiguity_flags) | {q for q, state in value.answered_questions.items() if state == PARTIALLY_RESOLVED}
        resolved_set = {q for q, state in value.answered_questions.items() if state == RESOLVED and q in explicit} - contradictory_set
        unresolved_set = known - resolved_set - contradictory_set
        resolved = tuple(q for q in ordered_questions if q in resolved_set)
        contradictory = tuple(q for q in ordered_questions if q in contradictory_set)
        unresolved = tuple(q for q in ordered_questions if q in unresolved_set)
        if contradictory:
            return _result(value, CONTRADICTORY, {"CONTRADICTORY_RESPONSE", "GATE_CHANGE_REQUIRES_SEPARATE_REVIEW"}, resolved=resolved, unresolved=unresolved, contradictory=contradictory, manual=True, next_required=unresolved)
        if ambiguous:
            reasons.add("AMBIGUOUS_RESPONSE")
        all_resolved = not unresolved and not ambiguous
        if all_resolved:
            return _result(value, RESOLVED, {"GATE_CHANGE_REQUIRES_SEPARATE_REVIEW"}, resolved=resolved, unlock=True, manual=True)
        reasons.update({"QUESTIONS_UNANSWERED", "PARTIAL_RESPONSE", "GATE_CHANGE_REQUIRES_SEPARATE_REVIEW"})
        return _result(value, PARTIALLY_RESOLVED if resolved else UNRESOLVED, reasons, resolved=resolved, unresolved=unresolved, unlock=False, manual=bool(ambiguous), next_required=unresolved)
    except Exception:
        return _result(None, FAIL_CLOSED, {"MALFORMED_INPUT"}, manual=True)


__all__ = [
    "CONTRADICTORY", "DIRECT_SUPPORT_CONFIRMATION", "DUPLICATE_CONFIRMATION",
    "FAIL_CLOSED", "INTAKE_VERSION", "LIFECYCLE_QUESTION_IDS",
    "OFFICIAL_DOCUMENTATION", "OfficialResponseIntakeResult",
    "PARTIALLY_RESOLVED", "QUESTION_STATES", "RESOLVED", "RIGHTS_BLOCKER",
    "SORT_QUESTION_IDS", "SanitizedOfficialResponse", "UNRESOLVED",
    "classify_official_response",
]
