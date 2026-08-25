"""Pure UI handoff contract for Affiliate Link Adapter safe results."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from affiliate_link_adapter import ADAPTER_VERSION, INVALID, VALID
from affiliate_link_policy import (
    LINK_AVAILABLE_FOR_UI,
    LINK_BLOCKED,
    LINK_NOT_AVAILABLE,
    LINK_PENDING_LIFECYCLE_POLICY,
)


HANDOFF_VERSION = "0.1"
RENDER_BLOCKED = "RENDER_BLOCKED"
RENDER_CANDIDATE = "RENDER_CANDIDATE"
RENDER_ALLOWED = "RENDER_ALLOWED"
INVALID_INPUT = "INVALID_INPUT"
RENDER_STATES = frozenset({RENDER_BLOCKED, RENDER_CANDIDATE, RENDER_ALLOWED, INVALID_INPUT})
WEB_UI = "WEB_UI"
BLOCKED_CONTEXTS = frozenset({"PUBLIC_JSON", "PUBLIC_DATA", "STATIC_EXPORT", "API_RESPONSE_EXPORT"})
SAFE_RESULT_FIELDS = frozenset({
    "adapter_version", "validation_status", "link_status", "ui_candidate",
    "production_render_allowed", "pr_disclosure_required", "reason_codes",
})
SAFE_REASON = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
KNOWN_ADAPTER_REASONS = frozenset({
    "AFFILIATE_ELIGIBILITY_NOT_CONFIRMED", "AVAILABILITY_NOT_INFERRED",
    "INTERNAL_ADAPTER_ERROR", "LIFECYCLE_SEMANTICS_PENDING",
    "LINK_VALUE_VALIDATED", "PUBLICATION_GATE_CLOSED",
    "PR_DISCLOSURE_REQUIRED", "PUBLIC_ARTIFACT_AFFILIATE_URL_FORBIDDEN",
    "PURCHASABILITY_NOT_CONFIRMED", "RIGHTS_NOT_CONDITIONALLY_APPROVED",
    "UI_RUNTIME_LINK_CANDIDATE", "UNSUPPORTED_ADAPTER_VERSION",
    "URL_CONTROL_CHARACTER", "URL_EMBEDDED_CREDENTIAL_FORBIDDEN",
    "URL_HOST_REQUIRED", "URL_LOCAL_PATH_FORBIDDEN", "URL_LOOPBACK_FORBIDDEN",
    "URL_MALFORMED", "URL_PORT_INVALID", "URL_SCHEME_FORBIDDEN",
    "URL_UNC_FORBIDDEN", "URL_WHITESPACE_FORBIDDEN", "VERIFICATION_FAILED",
    "VERIFICATION_PENDING", "GATE_STATUS_MALFORMED", "INTERNAL_POLICY_ERROR",
    "UNKNOWN_LIFECYCLE_STATUS", "UNKNOWN_PUBLICATION_CONTEXT",
    "UNKNOWN_PUBLICATION_GATE_STATUS", "UNKNOWN_RIGHTS_STATUS",
    "UNKNOWN_VERIFICATION_STATUS", "UNSUPPORTED_POLICY_VERSION",
})


@dataclass(frozen=True)
class UIHandoffResult:
    handoff_version: str
    render_status: str
    render_candidate: bool
    render_allowed: bool
    pr_disclosure_required: bool
    target_context: str | None
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **{key: value for key, value in self.__dict__.items() if key != "reason_codes"},
            "reason_codes": list(self.reason_codes),
        }


def _result(
    status: str,
    *,
    candidate: bool = False,
    allowed: bool = False,
    context: str | None = None,
    reasons: tuple[str, ...],
) -> UIHandoffResult:
    return UIHandoffResult(
        HANDOFF_VERSION, status, candidate, allowed, True, context,
        tuple(sorted(set(reasons))),
    )


def _valid_adapter_result(value: Any) -> tuple[bool, tuple[str, ...]]:
    if not isinstance(value, Mapping) or set(value) != SAFE_RESULT_FIELDS:
        return False, ("ADAPTER_RESULT_SCHEMA_INVALID",)
    if value["adapter_version"] != ADAPTER_VERSION:
        return False, ("ADAPTER_VERSION_UNSUPPORTED",)
    if value["validation_status"] not in {VALID, INVALID}:
        return False, ("VALIDATION_STATUS_UNKNOWN",)
    if value["link_status"] not in {
        LINK_AVAILABLE_FOR_UI, LINK_NOT_AVAILABLE,
        LINK_PENDING_LIFECYCLE_POLICY, LINK_BLOCKED, "INVALID_INPUT",
    }:
        return False, ("LINK_STATUS_UNKNOWN",)
    if any(not isinstance(value[key], bool) for key in ("ui_candidate", "production_render_allowed", "pr_disclosure_required")):
        return False, ("ADAPTER_FLAGS_MALFORMED",)
    if value["pr_disclosure_required"] is not True:
        return False, ("PR_REQUIREMENT_CONTRADICTION",)
    reasons = value["reason_codes"]
    if (
        not isinstance(reasons, (list, tuple))
        or not reasons
        or any(not isinstance(reason, str) or not SAFE_REASON.fullmatch(reason) or reason not in KNOWN_ADAPTER_REASONS for reason in reasons)
    ):
        return False, ("ADAPTER_REASON_UNKNOWN",)
    if (
        value["production_render_allowed"] and not value["ui_candidate"]
        or value["validation_status"] != VALID and (value["ui_candidate"] or value["production_render_allowed"])
        or value["link_status"] in {LINK_BLOCKED, LINK_NOT_AVAILABLE, "INVALID_INPUT"} and value["ui_candidate"]
        or value["link_status"] != LINK_AVAILABLE_FOR_UI and value["production_render_allowed"]
    ):
        return False, ("ADAPTER_FLAGS_CONTRADICTORY",)
    return True, ()


def _handoff(
    *,
    handoff_version: Any,
    adapter_result: Any,
    target_context: Any,
    disclosure_available: Any,
) -> UIHandoffResult:
    if handoff_version != HANDOFF_VERSION:
        return _result(INVALID_INPUT, reasons=("HANDOFF_VERSION_UNSUPPORTED",))
    if target_context in BLOCKED_CONTEXTS:
        return _result(RENDER_BLOCKED, context=target_context, reasons=("TARGET_CONTEXT_FORBIDDEN",))
    if target_context != WEB_UI:
        return _result(INVALID_INPUT, reasons=("TARGET_CONTEXT_UNKNOWN",))
    if not isinstance(disclosure_available, bool):
        return _result(INVALID_INPUT, context=WEB_UI, reasons=("DISCLOSURE_FLAG_MALFORMED",))
    valid, reasons = _valid_adapter_result(adapter_result)
    if not valid:
        return _result(INVALID_INPUT, context=WEB_UI, reasons=reasons)
    candidate = (
        adapter_result["validation_status"] == VALID
        and adapter_result["ui_candidate"] is True
    )
    if not disclosure_available:
        return _result(
            RENDER_BLOCKED, candidate=candidate, context=WEB_UI,
            reasons=("PR_DISCLOSURE_UNAVAILABLE",),
        )
    if not candidate:
        return _result(RENDER_BLOCKED, context=WEB_UI, reasons=("UI_CANDIDATE_REQUIRED",))
    if adapter_result["production_render_allowed"] is not True:
        return _result(
            RENDER_BLOCKED, candidate=True, context=WEB_UI,
            reasons=("ADAPTER_PRODUCTION_RENDER_BLOCKED",),
        )
    return _result(
        RENDER_ALLOWED, candidate=True, allowed=True, context=WEB_UI,
        reasons=("DELEGATED_RENDER_CONDITIONS_SATISFIED",),
    )


def build_ui_handoff(**kwargs: Any) -> UIHandoffResult:
    """Return a minimal instruction without accepting or returning a URL."""

    try:
        return _handoff(**kwargs)
    except Exception:
        return _result(INVALID_INPUT, reasons=("INTERNAL_HANDOFF_ERROR",))


__all__ = [
    "HANDOFF_VERSION", "INVALID_INPUT", "RENDER_ALLOWED", "RENDER_BLOCKED",
    "RENDER_CANDIDATE", "RENDER_STATES", "UIHandoffResult", "WEB_UI",
    "build_ui_handoff",
]
