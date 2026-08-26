"""Pure security and disclosure policy for future public UI links."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence

from affiliate_ui_handoff import HANDOFF_VERSION, INVALID_INPUT as HANDOFF_INVALID


POLICY_VERSION = "0.1"
BLOCKED_UPSTREAM = "BLOCKED_UPSTREAM"
UI_SECURITY_PASS = "UI_SECURITY_PASS"
UI_SECURITY_BLOCKED = "UI_SECURITY_BLOCKED"
INVALID_INPUT = "INVALID_INPUT"

NORMAL_EXTERNAL_LINK = "NORMAL_EXTERNAL_LINK"
AFFILIATE_LINK = "AFFILIATE_LINK"
INTERNAL_LINK = "INTERNAL_LINK"
LINK_TYPES = frozenset({NORMAL_EXTERNAL_LINK, AFFILIATE_LINK, INTERNAL_LINK})

REL_SPONSORED_REQUIRED = True
EXTERNAL_BASE_REL = frozenset({"noopener", "noreferrer"})
AFFILIATE_REL = EXTERNAL_BASE_REL | {"sponsored"}
ALLOWED_CTA_SEMANTICS = frozenset({"VIEW_PRODUCT", "OPEN_PRODUCT_PAGE", "CHECK_DETAILS"})
AMBIGUOUS_CTA_SEMANTICS = frozenset({"DOWNLOAD", "CONTINUE", "NEXT", "OPEN"})
PROHIBITED_PATTERNS = frozenset({
    "FAKE_DOWNLOAD_BUTTON", "FAKE_CLOSE_BUTTON", "DECEPTIVE_URGENCY",
    "FAKE_SCARCITY", "HIDDEN_DISCLOSURE", "PRESELECTED_CONSENT",
    "CONFUSING_BUTTON_LABEL", "AFFILIATE_LINK_DISGUISED",
    "DESTINATION_MISREPRESENTED", "AUTOMATIC_REDIRECT",
    "CLICK_INTERCEPTION", "FORCED_NEW_TAB_WITHOUT_USER_ACTION",
})
HANDOFF_FIELDS = frozenset({
    "handoff_version", "render_status", "render_candidate", "render_allowed",
    "pr_disclosure_required", "target_context", "reason_codes",
})
SAFE_REASON = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")


@dataclass(frozen=True)
class UISecurityResult:
    policy_version: str
    ui_security_status: str
    render_allowed: bool
    disclosure_required: bool
    external_indicator_required: bool
    required_rel_tokens: tuple[str, ...]
    prohibited_pattern_codes: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **{
                key: list(value) if key in {"required_rel_tokens", "prohibited_pattern_codes"} else value
                for key, value in self.__dict__.items()
                if key != "reason_codes"
            },
            "reason_codes": list(self.reason_codes),
        }


def _result(
    status: str,
    *,
    allowed: bool = False,
    disclosure: bool = False,
    external_indicator: bool = False,
    rel_tokens: Sequence[str] = (),
    patterns: Sequence[str] = (),
    reasons: Sequence[str],
) -> UISecurityResult:
    return UISecurityResult(
        POLICY_VERSION, status, allowed, disclosure, external_indicator,
        tuple(sorted(set(rel_tokens))), tuple(sorted(set(patterns))),
        tuple(sorted(set(reasons))),
    )


def _valid_handoff(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == HANDOFF_FIELDS
        and value["handoff_version"] == HANDOFF_VERSION
        and value["render_status"] in {"RENDER_BLOCKED", "RENDER_CANDIDATE", "RENDER_ALLOWED", HANDOFF_INVALID}
        and all(isinstance(value[key], bool) for key in ("render_candidate", "render_allowed", "pr_disclosure_required"))
        and value["pr_disclosure_required"] is True
        and value["target_context"] in {"WEB_UI", None}
        and isinstance(value["reason_codes"], (list, tuple))
        and bool(value["reason_codes"])
        and all(isinstance(reason, str) and SAFE_REASON.fullmatch(reason) for reason in value["reason_codes"])
        and not (value["render_allowed"] and value["render_status"] != "RENDER_ALLOWED")
        and not (value["render_allowed"] and not value["render_candidate"])
        and not (value["render_status"] == "RENDER_ALLOWED" and not value["render_allowed"])
    )


def _evaluate(
    *,
    policy_version: Any,
    handoff_result: Any,
    link_type: Any,
    disclosure_available: Any,
    disclosure_proximate: Any,
    disclosure_visible: Any,
    external_indicator_available: Any,
    target_blank: Any,
    rel_tokens: Any,
    cta_semantic: Any,
    prohibited_patterns: Any,
    user_initiated_navigation: Any,
    availability_claim: Any,
    purchasability_claim: Any,
    affiliate_eligibility_claim: Any,
) -> UISecurityResult:
    if policy_version != POLICY_VERSION:
        return _result(INVALID_INPUT, reasons=("UNSUPPORTED_POLICY_VERSION",))
    if not _valid_handoff(handoff_result):
        return _result(INVALID_INPUT, reasons=("HANDOFF_RESULT_INVALID",))
    if link_type not in LINK_TYPES:
        return _result(INVALID_INPUT, reasons=("LINK_TYPE_UNKNOWN",))
    boolean_values = (
        disclosure_available, disclosure_proximate, disclosure_visible,
        external_indicator_available, target_blank, user_initiated_navigation,
        availability_claim, purchasability_claim, affiliate_eligibility_claim,
    )
    if any(not isinstance(value, bool) for value in boolean_values):
        return _result(INVALID_INPUT, reasons=("BOOLEAN_INPUT_INVALID",))
    if (
        not isinstance(rel_tokens, (list, tuple, set, frozenset))
        or any(not isinstance(token, str) or token.casefold() != token or not token for token in rel_tokens)
        or not isinstance(prohibited_patterns, (list, tuple, set, frozenset))
        or any(pattern not in PROHIBITED_PATTERNS for pattern in prohibited_patterns)
    ):
        return _result(INVALID_INPUT, reasons=("SECURITY_INPUT_INVALID",))
    disclosure_required = link_type == AFFILIATE_LINK
    external_required = link_type in {NORMAL_EXTERNAL_LINK, AFFILIATE_LINK}
    required_rel = AFFILIATE_REL if link_type == AFFILIATE_LINK else EXTERNAL_BASE_REL if external_required and target_blank else frozenset()
    if handoff_result["render_allowed"] is not True:
        return _result(
            BLOCKED_UPSTREAM, disclosure=disclosure_required,
            external_indicator=external_required, rel_tokens=required_rel,
            reasons=("UPSTREAM_RENDER_BLOCKED",),
        )
    reasons: list[str] = []
    violations = tuple(sorted(set(prohibited_patterns)))
    if violations:
        reasons.append("DARK_PATTERN_DETECTED")
    if any((availability_claim, purchasability_claim, affiliate_eligibility_claim)):
        reasons.append("UNRESOLVED_LIFECYCLE_CLAIM_FORBIDDEN")
    if link_type == AFFILIATE_LINK and (
        not disclosure_available or not disclosure_proximate or not disclosure_visible
    ):
        reasons.append("AFFILIATE_DISCLOSURE_INADEQUATE")
    if external_required and not external_indicator_available:
        reasons.append("EXTERNAL_INDICATOR_REQUIRED")
    if target_blank and not user_initiated_navigation:
        reasons.append("FORCED_NEW_TAB_FORBIDDEN")
    normalized_rel = frozenset(rel_tokens)
    missing = required_rel - normalized_rel
    if missing:
        reasons.append("REQUIRED_REL_TOKEN_MISSING")
    if link_type == INTERNAL_LINK and (target_blank or normalized_rel or external_indicator_available):
        reasons.append("LINK_TYPE_CONTRADICTION")
    if not isinstance(cta_semantic, str) or cta_semantic not in ALLOWED_CTA_SEMANTICS:
        reasons.append("CTA_SEMANTIC_UNSAFE" if cta_semantic in AMBIGUOUS_CTA_SEMANTICS else "CTA_SEMANTIC_UNKNOWN")
    if reasons:
        return _result(
            UI_SECURITY_BLOCKED, disclosure=disclosure_required,
            external_indicator=external_required, rel_tokens=required_rel,
            patterns=violations, reasons=reasons,
        )
    return _result(
        UI_SECURITY_PASS, allowed=True, disclosure=disclosure_required,
        external_indicator=external_required, rel_tokens=required_rel,
        reasons=("UI_SECURITY_REQUIREMENTS_SATISFIED",),
    )


def assess_ui_security(**kwargs: Any) -> UISecurityResult:
    """Apply safety requirements without accepting a URL or mutating UI state."""

    try:
        return _evaluate(**kwargs)
    except Exception:
        return _result(INVALID_INPUT, reasons=("INTERNAL_UI_SECURITY_ERROR",))


__all__ = [
    "AFFILIATE_LINK", "BLOCKED_UPSTREAM", "INTERNAL_LINK", "INVALID_INPUT",
    "NORMAL_EXTERNAL_LINK", "POLICY_VERSION", "PROHIBITED_PATTERNS",
    "REL_SPONSORED_REQUIRED", "UISecurityResult", "UI_SECURITY_BLOCKED",
    "UI_SECURITY_PASS", "assess_ui_security",
]
