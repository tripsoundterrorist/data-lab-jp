"""Pure integration readiness for the four affiliate UI safety layers."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

import affiliate_link_adapter
import affiliate_link_policy
import affiliate_ui_handoff
import ui_security_disclosure_policy


READINESS_VERSION = "0.1"
BLOCKED = "BLOCKED"
INTERNALLY_READY = "INTERNALLY_READY"
PRODUCTION_CANDIDATE = "PRODUCTION_CANDIDATE"
INVALID_INPUT = "INVALID_INPUT"
MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"

PASS = "PASS"
CLOSED = "CLOSED"
PENDING = "PENDING_OFFICIAL_CONFIRMATION"
RESOLVED = "RESOLVED"
GATE_STATUSES = frozenset({PASS, CLOSED})
OFFICIAL_STATUSES = frozenset({PENDING, RESOLVED})
SAFE_REASON = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")

POLICY_FIELDS = frozenset({
    "policy_version", "link_status", "ui_candidate", "production_render_allowed",
    "pr_disclosure_required", "lifecycle_semantics_resolved", "reason_codes",
})
ADAPTER_FIELDS = frozenset({
    "adapter_version", "validation_status", "link_status", "ui_candidate",
    "production_render_allowed", "pr_disclosure_required", "reason_codes",
})
HANDOFF_FIELDS = frozenset({
    "handoff_version", "render_status", "render_candidate", "render_allowed",
    "pr_disclosure_required", "target_context", "reason_codes",
})
SECURITY_FIELDS = frozenset({
    "policy_version", "ui_security_status", "render_allowed",
    "disclosure_required", "external_indicator_required", "required_rel_tokens",
    "prohibited_pattern_codes", "reason_codes",
})
COMPONENT_NAMES = (
    "affiliate_link_policy", "affiliate_link_adapter",
    "affiliate_ui_handoff", "ui_security_disclosure",
)
POLICY_LINK_STATUSES_V01 = affiliate_link_policy.LINK_STATUSES
ADAPTER_VALIDATION_STATUSES_V01 = frozenset({
    affiliate_link_adapter.VALID, affiliate_link_adapter.INVALID,
})
HANDOFF_RENDER_STATUSES_V01 = affiliate_ui_handoff.RENDER_STATES
SECURITY_STATUSES_V01 = frozenset({
    ui_security_disclosure_policy.BLOCKED_UPSTREAM,
    ui_security_disclosure_policy.UI_SECURITY_PASS,
    ui_security_disclosure_policy.UI_SECURITY_BLOCKED,
    ui_security_disclosure_policy.INVALID_INPUT,
})
POLICY_REASONS_V01 = frozenset({
    "AFFILIATE_ELIGIBILITY_NOT_CONFIRMED", "AFFILIATE_INELIGIBILITY_NOT_INFERRED",
    "AVAILABILITY_NOT_INFERRED", "INTERNAL_POLICY_ERROR",
    "LIFECYCLE_SEMANTICS_PENDING", "LIFECYCLE_STATE_CONTRADICTION",
    "MALFORMED_BOOLEAN", "NO_LINK_VALUE_FOR_UI", "PR_DISCLOSURE_REQUIRED",
    "PUBLIC_ARTIFACT_AFFILIATE_URL_FORBIDDEN", "PUBLICATION_GATE_CLOSED",
    "PURCHASABILITY_NOT_CONFIRMED", "RIGHTS_NOT_CONDITIONALLY_APPROVED",
    "UI_RUNTIME_LINK_CANDIDATE", "UNKNOWN_LIFECYCLE_STATUS",
    "UNKNOWN_PUBLICATION_CONTEXT", "UNKNOWN_PUBLICATION_GATE_STATUS",
    "UNKNOWN_RIGHTS_STATUS", "UNKNOWN_VERIFICATION_STATUS",
    "UNSUPPORTED_POLICY_VERSION", "VERIFICATION_FAILED", "VERIFICATION_PENDING",
})
ADAPTER_REASONS_V01 = POLICY_REASONS_V01 | frozenset({
    "GATE_STATUS_MALFORMED", "INTERNAL_ADAPTER_ERROR", "LINK_VALUE_VALIDATED",
    "UNSUPPORTED_ADAPTER_VERSION", "URL_CONTROL_CHARACTER",
    "URL_EMBEDDED_CREDENTIAL_FORBIDDEN", "URL_HOST_REQUIRED",
    "URL_LOCAL_PATH_FORBIDDEN", "URL_LOOPBACK_FORBIDDEN", "URL_MALFORMED",
    "URL_PORT_INVALID", "URL_SCHEME_FORBIDDEN", "URL_UNC_FORBIDDEN",
    "URL_WHITESPACE_FORBIDDEN",
})
HANDOFF_REASONS_V01 = ui_security_disclosure_policy.KNOWN_HANDOFF_REASONS_V01
SECURITY_REASONS_V01 = frozenset({
    "AFFILIATE_DISCLOSURE_INADEQUATE", "BOOLEAN_INPUT_INVALID",
    "CTA_SEMANTIC_UNKNOWN", "CTA_SEMANTIC_UNSAFE", "DARK_PATTERN_DETECTED",
    "EXTERNAL_INDICATOR_REQUIRED", "FORCED_NEW_TAB_FORBIDDEN",
    "HANDOFF_RESULT_INVALID", "INTERNAL_UI_SECURITY_ERROR",
    "LINK_TYPE_CONTRADICTION", "LINK_TYPE_UNKNOWN", "REQUIRED_REL_TOKEN_MISSING",
    "SECURITY_INPUT_INVALID", "UI_SECURITY_REQUIREMENTS_SATISFIED",
    "UNRESOLVED_LIFECYCLE_CLAIM_FORBIDDEN", "UNSUPPORTED_POLICY_VERSION",
    "UPSTREAM_RENDER_BLOCKED",
})


@dataclass(frozen=True)
class PublicationUIReadinessResult:
    readiness_version: str
    overall_readiness: str
    all_internal_components_ready: bool
    production_integration_allowed: bool
    publication_gate_status: str | None
    lifecycle_status: str | None
    semantics_status: str | None
    component_statuses: tuple[tuple[str, str], ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **{
                key: ({name: status for name, status in value} if key == "component_statuses" else value)
                for key, value in self.__dict__.items()
                if key != "reason_codes"
            },
            "reason_codes": list(self.reason_codes),
        }


def _result(
    overall: str,
    gate: Any,
    lifecycle: Any,
    semantics: Any,
    *,
    components_ready: bool = False,
    production_allowed: bool = False,
    component_statuses: tuple[tuple[str, str], ...] = (),
    reasons: tuple[str, ...],
) -> PublicationUIReadinessResult:
    return PublicationUIReadinessResult(
        READINESS_VERSION, overall, components_ready, production_allowed,
        gate if isinstance(gate, str) else None,
        lifecycle if isinstance(lifecycle, str) else None,
        semantics if isinstance(semantics, str) else None,
        component_statuses, tuple(sorted(set(reasons))),
    )


def _mapping(value: Any, fields: frozenset[str]) -> bool:
    return isinstance(value, Mapping) and set(value) == fields


def _reasons_valid(value: Any, known: frozenset[str]) -> bool:
    return (
        isinstance(value, (list, tuple)) and bool(value)
        and all(
            isinstance(reason, str)
            and SAFE_REASON.fullmatch(reason)
            and reason in known
            for reason in value
        )
    )


def _status_flags_valid(policy: Mapping[str, Any], adapter: Mapping[str, Any], handoff: Mapping[str, Any], security: Mapping[str, Any]) -> bool:
    policy_status = policy["link_status"]
    adapter_status = adapter["link_status"]
    return (
        policy_status in POLICY_LINK_STATUSES_V01
        and adapter["validation_status"] in ADAPTER_VALIDATION_STATUSES_V01
        and adapter_status in POLICY_LINK_STATUSES_V01
        and handoff["render_status"] in HANDOFF_RENDER_STATUSES_V01
        and security["ui_security_status"] in SECURITY_STATUSES_V01
        and not (policy_status == affiliate_link_policy.LINK_AVAILABLE_FOR_UI and not policy["ui_candidate"])
        and not (policy["production_render_allowed"] and (not policy["ui_candidate"] or not policy["lifecycle_semantics_resolved"]))
        and not (adapter["validation_status"] == affiliate_link_adapter.INVALID and (adapter_status != affiliate_link_policy.INVALID_INPUT or adapter["ui_candidate"] or adapter["production_render_allowed"]))
        and not (adapter_status in {affiliate_link_policy.LINK_BLOCKED, affiliate_link_policy.LINK_NOT_AVAILABLE, affiliate_link_policy.INVALID_INPUT} and (adapter["ui_candidate"] or adapter["production_render_allowed"]))
        and not (adapter_status == affiliate_link_policy.LINK_AVAILABLE_FOR_UI and not adapter["ui_candidate"])
        and not (adapter["production_render_allowed"] and adapter["validation_status"] != affiliate_link_adapter.VALID)
        and not (handoff["render_status"] == affiliate_ui_handoff.RENDER_ALLOWED and (not handoff["render_candidate"] or not handoff["render_allowed"]))
        and not (handoff["render_status"] == affiliate_ui_handoff.RENDER_CANDIDATE and (not handoff["render_candidate"] or handoff["render_allowed"]))
        and not (handoff["render_status"] in {affiliate_ui_handoff.RENDER_BLOCKED, affiliate_ui_handoff.INVALID_INPUT} and handoff["render_allowed"])
        and not (security["ui_security_status"] == ui_security_disclosure_policy.UI_SECURITY_PASS and not security["render_allowed"])
        and not (security["ui_security_status"] != ui_security_disclosure_policy.UI_SECURITY_PASS and security["render_allowed"])
    )


def _components_valid(policy: Any, adapter: Any, handoff: Any, security: Any) -> tuple[bool, tuple[tuple[str, str], ...], tuple[str, ...]]:
    values = (policy, adapter, handoff, security)
    schemas = (POLICY_FIELDS, ADAPTER_FIELDS, HANDOFF_FIELDS, SECURITY_FIELDS)
    known_reasons = (
        POLICY_REASONS_V01, ADAPTER_REASONS_V01,
        HANDOFF_REASONS_V01, SECURITY_REASONS_V01,
    )
    statuses: list[tuple[str, str]] = []
    reasons: list[str] = []
    for name, value, schema, reasons_allowlist in zip(COMPONENT_NAMES, values, schemas, known_reasons):
        valid = _mapping(value, schema) and _reasons_valid(
            value.get("reason_codes") if isinstance(value, Mapping) else None,
            reasons_allowlist,
        )
        statuses.append((name, "READY" if valid else "INVALID"))
        if not valid:
            reasons.append(f"{name.upper()}_CONTRACT_INVALID")
    if reasons:
        return False, tuple(statuses), tuple(reasons)
    versions = (
        policy["policy_version"] == affiliate_link_policy.POLICY_VERSION,
        adapter["adapter_version"] == affiliate_link_adapter.ADAPTER_VERSION,
        handoff["handoff_version"] == affiliate_ui_handoff.HANDOFF_VERSION,
        security["policy_version"] == ui_security_disclosure_policy.POLICY_VERSION,
    )
    if not all(versions):
        statuses = [(name, "READY" if version else "UNKNOWN_VERSION") for name, version in zip(COMPONENT_NAMES, versions)]
        return False, tuple(statuses), ("COMPONENT_VERSION_UNKNOWN",)
    boolean_fields = (
        (policy, ("ui_candidate", "production_render_allowed", "pr_disclosure_required", "lifecycle_semantics_resolved")),
        (adapter, ("ui_candidate", "production_render_allowed", "pr_disclosure_required")),
        (handoff, ("render_candidate", "render_allowed", "pr_disclosure_required")),
        (security, ("render_allowed", "disclosure_required", "external_indicator_required")),
    )
    if any(not isinstance(value[field], bool) for value, fields in boolean_fields for field in fields):
        return False, tuple((name, "INVALID") for name in COMPONENT_NAMES), ("COMPONENT_FLAGS_INVALID",)
    if not _status_flags_valid(policy, adapter, handoff, security):
        return False, tuple((name, "INVALID") for name in COMPONENT_NAMES), ("COMPONENT_STATUS_OR_FLAGS_INVALID",)
    if policy["pr_disclosure_required"] is not True or adapter["pr_disclosure_required"] is not True or handoff["pr_disclosure_required"] is not True:
        return False, tuple((name, "INVALID") for name in COMPONENT_NAMES), ("PR_REQUIREMENT_NOT_PRESERVED",)
    if not isinstance(security["required_rel_tokens"], (list, tuple)) or not isinstance(security["prohibited_pattern_codes"], (list, tuple)):
        return False, tuple((name, "INVALID") for name in COMPONENT_NAMES), ("SECURITY_OUTPUT_INVALID",)
    return True, tuple((name, "READY") for name in COMPONENT_NAMES), ()


def _contradictions(policy: Mapping[str, Any], adapter: Mapping[str, Any], handoff: Mapping[str, Any], security: Mapping[str, Any]) -> tuple[str, ...]:
    reasons: list[str] = []
    if policy["link_status"] in {"LINK_BLOCKED", "LINK_NOT_AVAILABLE", "INVALID_INPUT"} and adapter["ui_candidate"]:
        reasons.append("POLICY_ADAPTER_CONTRADICTION")
    if not policy["production_render_allowed"] and adapter["production_render_allowed"]:
        reasons.append("POLICY_ADAPTER_CONTRADICTION")
    if not adapter["production_render_allowed"] and handoff["render_allowed"]:
        reasons.append("ADAPTER_HANDOFF_CONTRADICTION")
    if not handoff["render_allowed"] and security["render_allowed"]:
        reasons.append("HANDOFF_SECURITY_CONTRADICTION")
    if adapter["production_render_allowed"] and not adapter["ui_candidate"]:
        reasons.append("ADAPTER_FLAGS_CONTRADICTORY")
    if handoff["render_allowed"] and not handoff["render_candidate"]:
        reasons.append("HANDOFF_FLAGS_CONTRADICTORY")
    if security["ui_security_status"] == "UI_SECURITY_PASS" and not security["render_allowed"]:
        reasons.append("SECURITY_FLAGS_CONTRADICTORY")
    return tuple(reasons)


def _assess(
    *,
    readiness_version: Any,
    affiliate_link_policy_result: Any,
    affiliate_link_adapter_result: Any,
    affiliate_ui_handoff_result: Any,
    ui_security_disclosure_result: Any,
    publication_gate_status: Any,
    lifecycle_status: Any,
    semantics_status: Any,
) -> PublicationUIReadinessResult:
    if readiness_version != READINESS_VERSION:
        return _result(INVALID_INPUT, publication_gate_status, lifecycle_status, semantics_status, reasons=("READINESS_VERSION_UNSUPPORTED",))
    if publication_gate_status not in GATE_STATUSES or lifecycle_status not in OFFICIAL_STATUSES or semantics_status not in OFFICIAL_STATUSES:
        return _result(INVALID_INPUT, publication_gate_status, lifecycle_status, semantics_status, reasons=("READINESS_STATUS_UNKNOWN",))
    valid, statuses, reasons = _components_valid(
        affiliate_link_policy_result, affiliate_link_adapter_result,
        affiliate_ui_handoff_result, ui_security_disclosure_result,
    )
    if not valid:
        return _result(INVALID_INPUT, publication_gate_status, lifecycle_status, semantics_status, component_statuses=statuses, reasons=reasons)
    contradictions = _contradictions(
        affiliate_link_policy_result, affiliate_link_adapter_result,
        affiliate_ui_handoff_result, ui_security_disclosure_result,
    )
    if contradictions:
        return _result(MANUAL_REVIEW_REQUIRED, publication_gate_status, lifecycle_status, semantics_status, components_ready=True, component_statuses=statuses, reasons=contradictions)
    blockers: list[str] = []
    if publication_gate_status != PASS:
        blockers.append("PUBLICATION_GATE_CLOSED")
    if lifecycle_status != RESOLVED:
        blockers.append("LIFECYCLE_OFFICIAL_CONFIRMATION_PENDING")
    if semantics_status != RESOLVED:
        blockers.append("SEMANTICS_OFFICIAL_CONFIRMATION_PENDING")
    downstream_allowed = (
        affiliate_link_policy_result["production_render_allowed"]
        and affiliate_link_adapter_result["production_render_allowed"]
        and affiliate_ui_handoff_result["render_allowed"]
        and ui_security_disclosure_result["render_allowed"]
    )
    if blockers:
        if downstream_allowed:
            return _result(MANUAL_REVIEW_REQUIRED, publication_gate_status, lifecycle_status, semantics_status, components_ready=True, component_statuses=statuses, reasons=("SECURITY_PASS_CANNOT_BYPASS_BLOCKERS",))
        return _result(BLOCKED, publication_gate_status, lifecycle_status, semantics_status, components_ready=True, component_statuses=statuses, reasons=tuple(blockers))
    if not downstream_allowed:
        return _result(INTERNALLY_READY, publication_gate_status, lifecycle_status, semantics_status, components_ready=True, component_statuses=statuses, reasons=("DOWNSTREAM_RENDER_NOT_ALLOWED",))
    return _result(PRODUCTION_CANDIDATE, publication_gate_status, lifecycle_status, semantics_status, components_ready=True, production_allowed=True, component_statuses=statuses, reasons=("PRODUCTION_INTEGRATION_CANDIDATE_ONLY", "DEPLOY_APPROVAL_REQUIRED"))


def assess_publication_ui_readiness(**kwargs: Any) -> PublicationUIReadinessResult:
    """Integrate safe summaries without changing any upstream state."""

    try:
        return _assess(**kwargs)
    except Exception:
        return _result(INVALID_INPUT, None, None, None, reasons=("INTERNAL_READINESS_ERROR",))


__all__ = [
    "BLOCKED", "INTERNALLY_READY", "INVALID_INPUT", "MANUAL_REVIEW_REQUIRED",
    "PRODUCTION_CANDIDATE", "PublicationUIReadinessResult", "READINESS_VERSION",
    "assess_publication_ui_readiness",
]
