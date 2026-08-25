"""Pure policy for conditional affiliate-link use in a Web UI.

No URL value is accepted or returned.  This module does not mutate publication,
lifecycle, blocker, database, artifact, or UI state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from official_blocker_policy import LIFECYCLE_BLOCKER, PENDING_OFFICIAL_CONFIRMATION, blocker_for
from rights_decision_policy import CONDITIONALLY_APPROVED, decision_for


POLICY_VERSION = "0.1"
WEB_UI = "WEB_UI"
PUBLIC_CONTEXTS = frozenset({"PUBLIC_JSON", "PUBLIC_DATA", "STATIC_ARTIFACT", "API_RESPONSE_EXPORT"})
CONTEXTS = PUBLIC_CONTEXTS | {WEB_UI}
LIFECYCLE_PENDING = "PENDING_OFFICIAL_CONFIRMATION"
LIFECYCLE_RESOLVED = "RESOLVED"
LIFECYCLE_STATUSES = frozenset({LIFECYCLE_PENDING, LIFECYCLE_RESOLVED})
VERIFICATION_PASS = "PASS"
VERIFICATION_PENDING = "PENDING"
VERIFICATION_FAILED = "FAILED"
VERIFICATION_STATUSES = frozenset({VERIFICATION_PASS, VERIFICATION_PENDING, VERIFICATION_FAILED})
GATE_OPEN = "OPEN"
GATE_CLOSED = "CLOSED"
GATE_STATUSES = frozenset({GATE_OPEN, GATE_CLOSED})

LINK_AVAILABLE_FOR_UI = "LINK_AVAILABLE_FOR_UI"
LINK_NOT_AVAILABLE = "LINK_NOT_AVAILABLE"
LINK_PENDING_LIFECYCLE_POLICY = "LINK_PENDING_LIFECYCLE_POLICY"
LINK_BLOCKED = "LINK_BLOCKED"
INVALID_INPUT = "INVALID_INPUT"
LINK_STATUSES = frozenset({
    LINK_AVAILABLE_FOR_UI, LINK_NOT_AVAILABLE, LINK_PENDING_LIFECYCLE_POLICY,
    LINK_BLOCKED, INVALID_INPUT,
})
PR_DISCLOSURE_REQUIRED = True


@dataclass(frozen=True)
class AffiliateLinkResult:
    policy_version: str
    link_status: str
    ui_candidate: bool
    production_render_allowed: bool
    pr_disclosure_required: bool
    lifecycle_semantics_resolved: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **{key: value for key, value in self.__dict__.items() if key != "reason_codes"},
            "reason_codes": list(self.reason_codes),
        }


def _result(
    status: str,
    *,
    ui_candidate: bool = False,
    production_render_allowed: bool = False,
    lifecycle_resolved: bool = False,
    reasons: tuple[str, ...],
) -> AffiliateLinkResult:
    return AffiliateLinkResult(
        POLICY_VERSION, status, ui_candidate, production_render_allowed,
        PR_DISCLOSURE_REQUIRED, lifecycle_resolved, tuple(sorted(set(reasons))),
    )


def _evaluate(
    *,
    policy_version: Any,
    rights_status: Any,
    publication_context: Any,
    has_affiliate_url: Any,
    lifecycle_status: Any,
    verification_status: Any,
    publication_gate_status: Any,
    pr_disclosure_available: Any,
) -> AffiliateLinkResult:
    if policy_version != POLICY_VERSION:
        return _result(INVALID_INPUT, reasons=("UNSUPPORTED_POLICY_VERSION",))
    values = (has_affiliate_url, pr_disclosure_available)
    if any(not isinstance(value, bool) for value in values):
        return _result(INVALID_INPUT, reasons=("MALFORMED_BOOLEAN",))
    if rights_status not in {"APPROVED", CONDITIONALLY_APPROVED, "PROHIBITED", "PENDING_SEPARATE_POLICY", "NOT_APPLICABLE"}:
        return _result(INVALID_INPUT, reasons=("UNKNOWN_RIGHTS_STATUS",))
    if publication_context not in CONTEXTS:
        return _result(INVALID_INPUT, reasons=("UNKNOWN_PUBLICATION_CONTEXT",))
    if lifecycle_status not in LIFECYCLE_STATUSES:
        return _result(INVALID_INPUT, reasons=("UNKNOWN_LIFECYCLE_STATUS",))
    if verification_status not in VERIFICATION_STATUSES:
        return _result(INVALID_INPUT, reasons=("UNKNOWN_VERIFICATION_STATUS",))
    if publication_gate_status not in GATE_STATUSES:
        return _result(INVALID_INPUT, reasons=("UNKNOWN_PUBLICATION_GATE_STATUS",))
    lifecycle_resolved = lifecycle_status == LIFECYCLE_RESOLVED
    if publication_context in PUBLIC_CONTEXTS:
        return _result(
            LINK_BLOCKED, lifecycle_resolved=lifecycle_resolved,
            reasons=("PUBLIC_ARTIFACT_AFFILIATE_URL_FORBIDDEN",),
        )
    rights_decision = decision_for("affiliate_url")
    if rights_decision.public_display != CONDITIONALLY_APPROVED or rights_status != CONDITIONALLY_APPROVED:
        return _result(
            LINK_BLOCKED, lifecycle_resolved=lifecycle_resolved,
            reasons=("RIGHTS_NOT_CONDITIONALLY_APPROVED",),
        )
    if not has_affiliate_url:
        return _result(
            LINK_NOT_AVAILABLE, lifecycle_resolved=lifecycle_resolved,
            reasons=("NO_LINK_VALUE_FOR_UI", "AFFILIATE_INELIGIBILITY_NOT_INFERRED"),
        )
    if not pr_disclosure_available:
        return _result(
            LINK_BLOCKED, lifecycle_resolved=lifecycle_resolved,
            reasons=("PR_DISCLOSURE_REQUIRED",),
        )
    if verification_status == VERIFICATION_FAILED:
        return _result(
            LINK_BLOCKED, lifecycle_resolved=lifecycle_resolved,
            reasons=("VERIFICATION_FAILED",),
        )
    if verification_status == VERIFICATION_PENDING:
        return _result(
            LINK_PENDING_LIFECYCLE_POLICY, lifecycle_resolved=lifecycle_resolved,
            reasons=("VERIFICATION_PENDING", "AVAILABILITY_NOT_INFERRED"),
        )
    if lifecycle_status == LIFECYCLE_PENDING:
        blocker = blocker_for(LIFECYCLE_BLOCKER)
        if blocker.status != PENDING_OFFICIAL_CONFIRMATION:
            return _result(INVALID_INPUT, reasons=("LIFECYCLE_STATE_CONTRADICTION",))
        return _result(
            LINK_PENDING_LIFECYCLE_POLICY, ui_candidate=True,
            lifecycle_resolved=False,
            reasons=("LIFECYCLE_SEMANTICS_PENDING", "AVAILABILITY_NOT_INFERRED", "PURCHASABILITY_NOT_CONFIRMED"),
        )
    production_allowed = publication_gate_status == GATE_OPEN
    reasons = ("UI_RUNTIME_LINK_CANDIDATE", "AFFILIATE_ELIGIBILITY_NOT_CONFIRMED", "PURCHASABILITY_NOT_CONFIRMED")
    if not production_allowed:
        reasons += ("PUBLICATION_GATE_CLOSED",)
    return _result(
        LINK_AVAILABLE_FOR_UI, ui_candidate=True,
        production_render_allowed=production_allowed,
        lifecycle_resolved=True, reasons=reasons,
    )


def assess_affiliate_link(**kwargs: Any) -> AffiliateLinkResult:
    """Assess sanitized booleans/statuses; reject URL-bearing extra input."""

    try:
        return _evaluate(**kwargs)
    except Exception:
        return _result(INVALID_INPUT, reasons=("INTERNAL_POLICY_ERROR",))


__all__ = [
    "AffiliateLinkResult", "GATE_CLOSED", "GATE_OPEN", "INVALID_INPUT",
    "LIFECYCLE_PENDING", "LIFECYCLE_RESOLVED", "LINK_AVAILABLE_FOR_UI",
    "LINK_BLOCKED", "LINK_NOT_AVAILABLE", "LINK_PENDING_LIFECYCLE_POLICY",
    "LINK_STATUSES", "POLICY_VERSION", "PR_DISCLOSURE_REQUIRED",
    "PUBLIC_CONTEXTS", "VERIFICATION_FAILED", "VERIFICATION_PASS",
    "VERIFICATION_PENDING", "WEB_UI", "assess_affiliate_link",
]
