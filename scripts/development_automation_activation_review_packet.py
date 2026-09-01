"""Build a minimal safe packet for manual activation review."""

from __future__ import annotations

from dataclasses import dataclass

import development_automation_activation_review_request as review_core


PACKET_VERSION = "0.1"


@dataclass(frozen=True)
class ActivationReviewPacket:
    packet_version: str
    status: str
    manual_review_ready: bool
    repository: str
    base_branch: str
    head_sha: str
    head_sha_short: str
    request_id: str
    source: str
    device_class: str
    scope: str
    review_window_seconds: int
    live_enabled: bool
    production_writes_enabled: bool
    additional_cost_required: bool
    approval_granted: bool
    activation_allowed: bool
    reason_codes: tuple[str, ...]


def _blocked(*reasons: str) -> ActivationReviewPacket:
    """Return a non-echoing packet for any rejected input."""
    return ActivationReviewPacket(
        PACKET_VERSION,
        "REVIEW_PACKET_BLOCKED",
        False,
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        0,
        False,
        False,
        False,
        False,
        False,
        tuple(reasons),
    )


def build(
    preflight_evidence: object,
    request: object,
    *,
    expected_head_sha: object,
    evaluated_at_epoch_s: object,
) -> ActivationReviewPacket:
    """Validate through the core contract and build a review-only packet."""
    decision = review_core.evaluate(
        preflight_evidence,
        request,
        expected_head_sha=expected_head_sha,
        evaluated_at_epoch_s=evaluated_at_epoch_s,
    )
    if (decision.status != "REVIEW_REQUEST_READY" or
            not decision.review_request_ready or
            decision.approval_granted or
            decision.activation_allowed):
        return _blocked(*decision.reason_codes)

    # Preserve fail-closed behavior even if the core contract changes later.
    if type(request) is not review_core.ActivationReviewRequest:
        return _blocked("REVIEW_REQUEST_TYPE_MISMATCH")
    return ActivationReviewPacket(
        PACKET_VERSION,
        "REVIEW_PACKET_READY",
        True,
        request.repository,
        request.base_branch,
        request.head_sha,
        request.head_sha[:12],
        request.request_id,
        request.source,
        request.device_class,
        request.scope,
        request.expires_at_epoch_s - request.requested_at_epoch_s,
        False,
        False,
        False,
        False,
        False,
        (
            "MANUAL_REVIEW_ONLY",
            "APPROVAL_NOT_GRANTED",
            "ACTIVATION_NOT_ALLOWED",
        ),
    )


__all__ = ["ActivationReviewPacket", "PACKET_VERSION", "build"]
