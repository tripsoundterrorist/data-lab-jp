"""Pure fail-closed preflight for development automation activation review."""

from __future__ import annotations

from dataclasses import dataclass


PREFLIGHT_VERSION = "0.1"
APPROVED_REPOSITORY = "tripsoundterrorist/data-lab-jp"
APPROVED_BASE = "main"
REQUIRED_ACTIONS = (
    "SAVE_CHECKPOINT",
    "RUN_TESTS",
    "COMMIT_AND_PUSH",
    "WAIT_FOR_CI",
    "REQUEST_APPROVAL",
    "START_NEXT_GATE",
)


@dataclass(frozen=True)
class ActivationPreflightEvidence:
    preflight_version: str
    repository: str
    base_branch: str
    configured_actions: tuple[str, ...]
    observation_chain_verified: bool
    fresh_usage_guard_required: bool
    blocked_checkpoint_required: bool
    blocked_safe_task_switch_required: bool
    operational_reserve_required: bool
    explicit_merge_approval_required: bool
    live_enabled: bool
    production_writes_enabled: bool
    additional_cost_required: bool


@dataclass(frozen=True)
class ActivationPreflightDecision:
    preflight_version: str
    status: str
    activation_allowed: bool
    manual_activation_review_required: bool
    reason_codes: tuple[str, ...]


def _decision(status: str, *reasons: str) -> ActivationPreflightDecision:
    return ActivationPreflightDecision(
        PREFLIGHT_VERSION,
        status,
        False,
        True,
        tuple(reasons),
    )


def evaluate(value: object) -> ActivationPreflightDecision:
    """Validate supplied evidence; never inspect, activate, write, or spend."""
    if type(value) is not ActivationPreflightEvidence:
        return _decision("PREFLIGHT_BLOCKED", "PREFLIGHT_EVIDENCE_INVALID")
    boolean_fields = (
        value.observation_chain_verified,
        value.fresh_usage_guard_required,
        value.blocked_checkpoint_required,
        value.blocked_safe_task_switch_required,
        value.operational_reserve_required,
        value.explicit_merge_approval_required,
        value.live_enabled,
        value.production_writes_enabled,
        value.additional_cost_required,
    )
    if not all(type(item) is bool for item in boolean_fields):
        return _decision("PREFLIGHT_BLOCKED", "PREFLIGHT_EVIDENCE_INVALID")
    if (value.preflight_version != PREFLIGHT_VERSION or
            value.repository != APPROVED_REPOSITORY or
            value.base_branch != APPROVED_BASE or
            type(value.configured_actions) is not tuple or
            value.configured_actions != REQUIRED_ACTIONS):
        return _decision("PREFLIGHT_BLOCKED", "PREFLIGHT_IDENTITY_INVALID")
    if value.live_enabled or value.production_writes_enabled:
        return _decision(
            "PREFLIGHT_BLOCKED",
            "LIVE_OR_PRODUCTION_WRITE_MUST_REMAIN_DISABLED",
        )
    if value.additional_cost_required:
        return _decision(
            "COST_CONFIRMATION_REQUIRED",
            "ADDITIONAL_COST_REQUIRES_CONFIRMATION",
        )

    protections = (
        value.observation_chain_verified,
        value.fresh_usage_guard_required,
        value.blocked_checkpoint_required,
        value.blocked_safe_task_switch_required,
        value.operational_reserve_required,
        value.explicit_merge_approval_required,
    )
    if not all(protections):
        return _decision(
            "PREFLIGHT_BLOCKED",
            "REQUIRED_SAFETY_PROTECTION_MISSING",
        )
    return _decision(
        "PREFLIGHT_READY_FOR_MANUAL_REVIEW",
        "SAFETY_EVIDENCE_COMPLETE",
        "PRODUCTION_ACTIVATION_NOT_IMPLEMENTED",
        "EXPLICIT_ACTIVATION_REVIEW_REQUIRED",
    )


__all__ = [
    "APPROVED_BASE", "APPROVED_REPOSITORY", "ActivationPreflightDecision",
    "ActivationPreflightEvidence", "PREFLIGHT_VERSION", "REQUIRED_ACTIONS",
    "evaluate",
]
