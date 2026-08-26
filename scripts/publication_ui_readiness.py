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


def _reasons_valid(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple)) and bool(value)
        and all(isinstance(reason, str) and SAFE_REASON.fullmatch(reason) for reason in value)
    )


def _components_valid(policy: Any, adapter: Any, handoff: Any, security: Any) -> tuple[bool, tuple[tuple[str, str], ...], tuple[str, ...]]:
    values = (policy, adapter, handoff, security)
    schemas = (POLICY_FIELDS, ADAPTER_FIELDS, HANDOFF_FIELDS, SECURITY_FIELDS)
    statuses: list[tuple[str, str]] = []
    reasons: list[str] = []
    for name, value, schema in zip(COMPONENT_NAMES, values, schemas):
        valid = _mapping(value, schema) and _reasons_valid(value.get("reason_codes") if isinstance(value, Mapping) else None)
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
