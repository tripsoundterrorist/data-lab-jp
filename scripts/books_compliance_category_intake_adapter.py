"""Adapt sanitized BOOKS answers to one explicitly named category intake."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

import books_compliance_scope_router as scope_router
import ebook_bl_compliance_response_intake as ebook_bl
import ebook_comic_compliance_response_intake as ebook_comic
import photo_book_compliance_response_intake as photo_book


VERSION = "0.1"
ADAPTED = "CATEGORY_INTAKE_ADAPTED"
BLOCKED = "CATEGORY_INTAKE_BLOCKED"

GROUPS = scope_router.QUESTION_GROUPS
STATES = frozenset(
    {
        ebook_comic.ALLOW,
        ebook_comic.DENY,
        ebook_comic.REQUIREMENTS,
        ebook_comic.UNRESOLVED,
        ebook_comic.CONFLICT,
    }
)
RESOLVED_STATES = ebook_comic.RESOLVED_STATES

_TARGETS = {
    scope_router.KNOWN_SCOPES[0]: (
        ebook_comic.SanitizedEbookComicComplianceResponse,
        ebook_comic.QUESTION_IDS,
        ebook_comic.classify,
    ),
    scope_router.KNOWN_SCOPES[1]: (
        ebook_bl.SanitizedEbookBlComplianceResponse,
        ebook_bl.QUESTION_IDS,
        ebook_bl.classify,
    ),
    scope_router.KNOWN_SCOPES[2]: (
        photo_book.SanitizedPhotoBookComplianceResponse,
        photo_book.QUESTION_IDS,
        photo_book.classify,
    ),
}


@dataclass(frozen=True)
class BooksCategoryIntakeRequest:
    response: scope_router.SanitizedBooksOfficialResponse
    group_states: Mapping[str, str]


@dataclass(frozen=True)
class BooksCategoryIntakeAdapterResult:
    version: str
    status: str
    target_scope: tuple[str, str, str, str] | None
    routing_status: str
    intake_status: str | None
    resolved_group_count: int
    unresolved_group_count: int
    contradictory_group_count: int
    separate_compliance_decision_candidate: bool
    compliance_approved: bool
    gate_change_allowed: bool
    publication_allowed: bool
    external_send_allowed: bool
    production_write_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        if self.target_scope is not None:
            result["target_scope"] = list(self.target_scope)
        result["reason_codes"] = list(self.reason_codes)
        return result


def _blocked(
    reason: str,
    *,
    target: tuple[str, str, str, str] | None = None,
    routing_status: str = scope_router.FAIL_CLOSED,
) -> BooksCategoryIntakeAdapterResult:
    return BooksCategoryIntakeAdapterResult(
        VERSION, BLOCKED, target, routing_status, None, 0, 0, 0,
        False, False, False, False, False, False, (reason,),
    )


def adapt(value: Any, target_scope: Any) -> BooksCategoryIntakeAdapterResult:
    if type(value) is not BooksCategoryIntakeRequest or type(target_scope) is not scope_router.BooksScope:
        return _blocked("MALFORMED_INPUT")
    try:
        target = target_scope.key()
        target_config = _TARGETS.get(target)
        if target_config is None:
            return _blocked("TARGET_SCOPE_UNKNOWN", target=target)

        routing = scope_router.route(value.response)
        if routing.status == scope_router.FAIL_CLOSED:
            return _blocked(
                "SCOPE_ROUTING_FAILED", target=target, routing_status=routing.status
            )
        if target not in routing.routed_scopes:
            return _blocked(
                "TARGET_SCOPE_NOT_EXPLICIT", target=target, routing_status=routing.status
            )

        states = dict(value.group_states)
        explicitly_answered = set(value.response.explicitly_answered_groups)
        if set(states) != explicitly_answered or any(state not in STATES for state in states.values()):
            return _blocked(
                "GROUP_STATE_SET_INVALID", target=target, routing_status=routing.status
            )

        response_type, question_ids, classifier = target_config
        question_states = {
            question_ids[index]: states.get(group, ebook_comic.UNRESOLVED)
            for index, group in enumerate(GROUPS)
        }
        explicit_ids = tuple(
            question_ids[index]
            for index, group in enumerate(GROUPS)
            if group in explicitly_answered
            and question_states[question_ids[index]] in RESOLVED_STATES
        )
        category_response = response_type(
            version=value.response.version,
            received_at=value.response.received_at,
            source_type=value.response.source_type,
            source_authority=value.response.source_authority,
            safe_reference=value.response.safe_reference,
            question_states=question_states,
            explicitly_answered_question_ids=explicit_ids,
        )
        intake = classifier(category_response)
        resolved = sum(state in RESOLVED_STATES for state in question_states.values())
        unresolved = sum(state == ebook_comic.UNRESOLVED for state in question_states.values())
        contradictory = sum(state == ebook_comic.CONFLICT for state in question_states.values())
        return BooksCategoryIntakeAdapterResult(
            VERSION,
            ADAPTED,
            target,
            routing.status,
            intake.status,
            resolved,
            unresolved,
            contradictory,
            intake.separate_compliance_decision_candidate,
            False,
            False,
            False,
            False,
            False,
            (
                "EXACT_SCOPE_ADAPTED",
                "CATEGORY_INTAKE_REMAINS_SEPARATE",
                "PUBLICATION_REMAINS_CLOSED",
            ),
        )
    except Exception:
        return _blocked("ADAPTER_FAILURE")


__all__ = ["BooksCategoryIntakeRequest", "BooksCategoryIntakeAdapterResult", "adapt"]
