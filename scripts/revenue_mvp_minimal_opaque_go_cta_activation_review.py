"""Pure aggregation gate for a minimal opaque CTA activation review request."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

import revenue_mvp_minimal_opaque_go_cta_artifact_preflight as artifact_preflight
import revenue_mvp_minimal_opaque_go_cta_contract as cta_contract
import revenue_mvp_minimal_opaque_go_cta_packet as packet_contract
import revenue_mvp_minimal_opaque_go_cta_renderer as renderer_contract


VERSION = "0.1-candidate"
READY = "READY_TO_REQUEST_EXPLICIT_ACTIVATION_REVIEW"
BLOCKED = "ACTIVATION_REVIEW_REQUEST_BLOCKED"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
FIELDS = frozenset({
    "contract_status", "packet_status", "renderer_status",
    "artifact_preflight_status", "artifact_sha256",
    "runtime_deployment_preflight_status", "compliance_artifact_approved",
    "explicit_user_activation_approval",
})


@dataclass(frozen=True)
class ActivationReviewDecision:
    version: str
    status: str
    ready_to_request_explicit_activation_review: bool
    artifact_sha256: str | None
    explicit_user_activation_approval_required: bool
    approval_granted: bool
    publication_allowed: bool
    production_activation_allowed: bool
    affiliate_eligibility_allowed: bool
    gate_mutation_allowed: bool
    d1_write_allowed: bool
    deployment_allowed: bool
    api_request_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _decision(
    status: str, ready: bool, digest: str | None, reasons: tuple[str, ...]
) -> ActivationReviewDecision:
    return ActivationReviewDecision(
        VERSION, status, ready, digest, True, False,
        False, False, False, False, False, False, False, reasons,
    )


def review(value: Any) -> ActivationReviewDecision:
    """Confirm review evidence only; never consume or infer activation approval."""

    try:
        if type(value) is not dict or set(value) != FIELDS:
            return _decision(BLOCKED, False, None, ("INPUT_CONTRACT_INVALID",))
        digest = value["artifact_sha256"]
        if type(digest) is not str or SHA256.fullmatch(digest) is None:
            return _decision(BLOCKED, False, None, ("ARTIFACT_DIGEST_INVALID",))
        expected = {
            "contract_status": cta_contract.READY,
            "packet_status": packet_contract.READY,
            "renderer_status": renderer_contract.READY,
            "artifact_preflight_status": artifact_preflight.PASS,
            "runtime_deployment_preflight_status": "READY_FOR_DEPLOYMENT_REVIEW",
        }
        for field, required in expected.items():
            if value[field] != required:
                return _decision(BLOCKED, False, digest, (f"{field.upper()}_INVALID",))
        if value["compliance_artifact_approved"] is not True:
            return _decision(BLOCKED, False, digest, ("COMPLIANCE_ARTIFACT_APPROVAL_REQUIRED",))
        if value["explicit_user_activation_approval"] is not False:
            return _decision(BLOCKED, False, digest, ("ACTIVATION_APPROVAL_MUST_NOT_BE_PRECONSUMED",))
        return _decision(
            READY,
            True,
            digest,
            (
                "ALL_REVIEW_ONLY_EVIDENCE_CONFIRMED",
                "EXPLICIT_USER_ACTIVATION_APPROVAL_REQUIRED",
                "ACTIVATION_REMAINS_CLOSED",
            ),
        )
    except Exception:
        return _decision(BLOCKED, False, None, ("ACTIVATION_REVIEW_ERROR",))


__all__ = [
    "ActivationReviewDecision", "BLOCKED", "READY", "VERSION", "review",
]
