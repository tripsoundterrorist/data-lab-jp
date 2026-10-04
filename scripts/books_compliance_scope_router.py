"""Route sanitized BOOKS official answers without cross-category inference."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import re
from typing import Any


VERSION = "0.1"
READY = "READY_FOR_CATEGORY_SPECIFIC_INTAKE"
PARTIAL = "PARTIAL_EXPLICIT_SCOPE"
FAIL_CLOSED = "FAIL_CLOSED"

DIRECT_SUPPORT = "DIRECT_SUPPORT_CONFIRMATION"
OFFICIAL_DOCS = "OFFICIAL_DOCUMENTATION"
EVIDENCE = frozenset(
    {
        (DIRECT_SUPPORT, "DMM_AFFILIATE_SUPPORT"),
        (OFFICIAL_DOCS, "DMM_OFFICIAL_DOCUMENTATION"),
    }
)

QUESTION_GROUPS = ("FIELD_USE", "IMAGE", "CONTRIBUTOR", "RETENTION")
KNOWN_SCOPES = (
    ("FANZA", "ebook", "comic", "ebook_comic"),
    ("FANZA", "ebook", "bl", "ebook_bl"),
    ("DMM.com", "ebook", "photo", "photo_book"),
)

_UNSAFE = re.compile(
    r"(?i)(?:https?://|file://|[a-z]:[\\/]|\\\\|\b[^\s@]+@[^\s@]+\.[^\s@]+\b|"
    r"(?:api|affiliate)[_-]?id\s*[:=]|(?:password|secret|token)\s*[:=])"
)


@dataclass(frozen=True)
class BooksScope:
    site: str
    service: str
    floor: str
    content_type: str

    def key(self) -> tuple[str, str, str, str]:
        return (self.site, self.service, self.floor, self.content_type)


@dataclass(frozen=True)
class SanitizedBooksOfficialResponse:
    version: str
    received_at: str
    source_type: str
    source_authority: str
    safe_reference: str
    explicitly_named_scopes: tuple[BooksScope, ...]
    explicitly_answered_groups: tuple[str, ...]


@dataclass(frozen=True)
class BooksScopeRoutingResult:
    version: str
    status: str
    routed_scopes: tuple[tuple[str, str, str, str], ...]
    pending_scopes: tuple[tuple[str, str, str, str], ...]
    answered_groups: tuple[str, ...]
    category_intake_allowed: bool
    compliance_approved: bool
    publication_allowed: bool
    external_send_allowed: bool
    production_write_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for key in ("routed_scopes", "pending_scopes", "answered_groups", "reason_codes"):
            result[key] = [list(row) if isinstance(row, tuple) else row for row in result[key]]
        return result


def _result(
    status: str,
    *,
    routed: tuple[tuple[str, str, str, str], ...] = (),
    pending: tuple[tuple[str, str, str, str], ...] = KNOWN_SCOPES,
    groups: tuple[str, ...] = (),
    intake: bool = False,
    reasons: tuple[str, ...],
) -> BooksScopeRoutingResult:
    return BooksScopeRoutingResult(
        VERSION, status, routed, pending, groups, intake,
        False, False, False, False, reasons,
    )


def _timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized).tzinfo is not None
    except ValueError:
        return False


def route(value: Any) -> BooksScopeRoutingResult:
    if type(value) is not SanitizedBooksOfficialResponse:
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

        scope_keys = tuple(scope.key() for scope in value.explicitly_named_scopes)
        if (
            not scope_keys
            or len(scope_keys) != len(set(scope_keys))
            or any(scope not in KNOWN_SCOPES for scope in scope_keys)
        ):
            return _result(FAIL_CLOSED, reasons=("EXPLICIT_SCOPE_SET_INVALID",))

        groups = value.explicitly_answered_groups
        if (
            not groups
            or len(groups) != len(set(groups))
            or any(group not in QUESTION_GROUPS for group in groups)
        ):
            return _result(FAIL_CLOSED, reasons=("EXPLICIT_GROUP_SET_INVALID",))

        routed = tuple(scope for scope in KNOWN_SCOPES if scope in set(scope_keys))
        pending = tuple(scope for scope in KNOWN_SCOPES if scope not in set(scope_keys))
        complete_groups = set(groups) == set(QUESTION_GROUPS)
        if pending or not complete_groups:
            return _result(
                PARTIAL,
                routed=routed,
                pending=pending,
                groups=tuple(group for group in QUESTION_GROUPS if group in set(groups)),
                reasons=(
                    "ONLY_EXPLICIT_SCOPE_ROUTED",
                    "CATEGORY_SPECIFIC_REMAINDER_REQUIRED",
                    "PUBLICATION_REMAINS_CLOSED",
                ),
            )
        return _result(
            READY,
            routed=routed,
            pending=(),
            groups=QUESTION_GROUPS,
            intake=True,
            reasons=(
                "ALL_BOOKS_SCOPES_AND_GROUPS_EXPLICIT",
                "SEPARATE_CATEGORY_INTAKES_REQUIRED",
                "PUBLICATION_REMAINS_CLOSED",
            ),
        )
    except Exception:
        return _result(FAIL_CLOSED, reasons=("MALFORMED_INPUT",))


__all__ = [
    "BooksScope",
    "SanitizedBooksOfficialResponse",
    "BooksScopeRoutingResult",
    "route",
]
