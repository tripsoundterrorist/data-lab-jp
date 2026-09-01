"""Pure validation for a development automation activation review request."""

from __future__ import annotations

from dataclasses import dataclass
import re

import development_automation_activation_preflight as preflight_core


REQUEST_VERSION = "0.1"
SOURCE = "CODEX_REMOTE"
DEVICE_CLASS = "IPHONE"
SCOPE = "DEVELOPMENT_AUTOMATION_CANDIDATE_ONLY"
MAX_REVIEW_WINDOW_SECONDS = 900
REQUEST_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
COMMIT_SHA = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True)
class ActivationReviewRequest:
    request_version: str
    source: str
    device_class: str
    repository: str
    base_branch: str
    request_id: str
    head_sha: str
    scope: str
    requested_at_epoch_s: int
    expires_at_epoch_s: int
    live_enabled: bool
    production_writes_enabled: bool
    additional_cost_required: bool


@dataclass(frozen=True)
class ActivationReviewRequestDecision:
    request_version: str
    status: str
    review_request_ready: bool
    approval_granted: bool
    activation_allowed: bool
    reason_codes: tuple[str, ...]


def _decision(
    status: str,
    ready: bool,
    *reasons: str,
) -> ActivationReviewRequestDecision:
    return ActivationReviewRequestDecision(
        REQUEST_VERSION,
        status,
        ready,
        False,
        False,
        tuple(reasons),
    )


def evaluate(
    preflight_evidence: object,
    request: object,
    *,
    expected_head_sha: object,
    evaluated_at_epoch_s: object,
) -> ActivationReviewRequestDecision:
    """Validate supplied evidence; never request approval or activate."""
    preflight = preflight_core.evaluate(preflight_evidence)
    if preflight.status != "PREFLIGHT_READY_FOR_MANUAL_REVIEW":
        return _decision(
            "REVIEW_REQUEST_BLOCKED",
            False,
            "ACTIVATION_PREFLIGHT_NOT_READY",
            *preflight.reason_codes,
        )
    if type(request) is not ActivationReviewRequest:
        return _decision(
            "REVIEW_REQUEST_BLOCKED", False, "REVIEW_REQUEST_INVALID"
        )
    booleans = (
        request.live_enabled,
        request.production_writes_enabled,
        request.additional_cost_required,
    )
    if not all(type(item) is bool for item in booleans):
        return _decision(
            "REVIEW_REQUEST_BLOCKED", False, "REVIEW_REQUEST_INVALID"
        )
    strings = (
        request.request_version,
        request.source,
        request.device_class,
        request.repository,
        request.base_branch,
        request.request_id,
        request.head_sha,
        request.scope,
    )
    if (not all(type(item) is str for item in strings) or
            request.request_version != REQUEST_VERSION or
            request.source != SOURCE or
            request.device_class != DEVICE_CLASS or
            request.repository != preflight_core.APPROVED_REPOSITORY or
            request.base_branch != preflight_core.APPROVED_BASE or
            request.scope != SCOPE or
            REQUEST_ID.fullmatch(request.request_id) is None or
            COMMIT_SHA.fullmatch(request.head_sha) is None):
        return _decision(
            "REVIEW_REQUEST_BLOCKED", False, "REVIEW_REQUEST_IDENTITY_INVALID"
        )
    if (type(expected_head_sha) is not str or
            COMMIT_SHA.fullmatch(expected_head_sha) is None or
            request.head_sha != expected_head_sha):
        return _decision(
            "REVIEW_REQUEST_BLOCKED", False, "REVIEW_REQUEST_TARGET_MISMATCH"
        )
    if request.live_enabled or request.production_writes_enabled:
        return _decision(
            "REVIEW_REQUEST_BLOCKED",
            False,
            "LIVE_OR_PRODUCTION_WRITE_MUST_REMAIN_DISABLED",
        )
    if request.additional_cost_required:
        return _decision(
            "COST_CONFIRMATION_REQUIRED",
            False,
            "ADDITIONAL_COST_REQUIRES_CONFIRMATION",
        )
    if (type(request.requested_at_epoch_s) is not int or
            type(request.expires_at_epoch_s) is not int or
            type(evaluated_at_epoch_s) is not int or
            request.requested_at_epoch_s < 0 or
            evaluated_at_epoch_s < request.requested_at_epoch_s or
            request.expires_at_epoch_s <= request.requested_at_epoch_s or
            evaluated_at_epoch_s > request.expires_at_epoch_s or
            request.expires_at_epoch_s - request.requested_at_epoch_s >
            MAX_REVIEW_WINDOW_SECONDS):
        return _decision(
            "REVIEW_REQUEST_BLOCKED", False, "REVIEW_WINDOW_INVALID"
        )
    return _decision(
        "REVIEW_REQUEST_READY",
        True,
        "ACTIVATION_REVIEW_REQUEST_VALIDATED",
        "APPROVAL_NOT_GRANTED",
        "ACTIVATION_NOT_ALLOWED",
    )


__all__ = [
    "ActivationReviewRequest", "ActivationReviewRequestDecision",
    "DEVICE_CLASS", "MAX_REVIEW_WINDOW_SECONDS", "REQUEST_VERSION", "SCOPE",
    "SOURCE", "evaluate",
]
