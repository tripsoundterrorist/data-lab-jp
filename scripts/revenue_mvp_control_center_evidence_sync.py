"""Pure, fail-closed synchronization of tracked Revenue MVP evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

import revenue_mvp_bounded_verification_runner as bounded_runner
import revenue_mvp_lifecycle_receipt as lifecycle_receipt
import revenue_mvp_official_lifecycle_policy as lifecycle_policy
import revenue_mvp_offline_artifact_integration as artifact_integration
import revenue_mvp_offline_launch_rehearsal as launch_rehearsal
import revenue_mvp_offline_lifecycle_filter as lifecycle_filter
import revenue_mvp_reduced_surface_gate_mapping as gate_mapping


VERSION = "0.1-candidate"
EVIDENCE_VERSION = "0.1"
SYNCED_BLOCKED = "CONTROL_CENTER_EVIDENCE_SYNCED_BLOCKED"
REVIEW_CANDIDATE = "CONTROL_CENTER_REDUCED_SURFACE_REVIEW_CANDIDATE"
FAIL_CLOSED = "CONTROL_CENTER_EVIDENCE_SYNC_FAIL_CLOSED"
REDUCED_SURFACE_ONLY = "REDUCED_SURFACE_ONLY"
RESPONSE_DATE = "2026-09-16"


@dataclass(frozen=True)
class ControlCenterEvidence:
    evidence_version: str
    official_response_received_on: str | None
    official_response_scope: str
    official_policy_version: str
    reduced_surface_mapping_version: str
    reduced_surface_mapping_status: str
    lifecycle_filter_version: str
    artifact_integration_version: str
    launch_rehearsal_version: str
    lifecycle_receipt_version: str
    bounded_runner_version: str
    builder_prefilter_verified: bool
    saved_receipts_fail_closed_verified: bool
    source_db_artifact_binding_verified: bool
    production_d1_read_only_reconfirmed: bool
    manual_reduced_surface_gate_approved: bool
    full_surface_official_confirmation_received: bool


@dataclass(frozen=True)
class ControlCenterEvidenceSync:
    version: str
    status: str
    official_response_pending: bool
    official_response_scope: str
    reduced_surface_review_candidate: bool
    full_surface_official_confirmation_pending: bool
    lifecycle_pipeline_verified: bool
    source_db_artifact_binding_verified: bool
    production_d1_read_only_reconfirmed: bool
    manual_reduced_surface_gate_approved: bool
    publication_allowed: bool
    production_activation_allowed: bool
    affiliate_eligibility_allowed: bool
    gate_mutation_allowed: bool
    next_action: str
    blocker_codes: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["blocker_codes"] = list(self.blocker_codes)
        value["reason_codes"] = list(self.reason_codes)
        return value


def current_tracked_evidence() -> ControlCenterEvidence:
    """Describe only merged contracts; operational facts stay unconfirmed."""

    mapping = gate_mapping.review_reduced_surface_gate_mapping(
        gate_mapping.current_versioned_evidence()
    )
    return ControlCenterEvidence(
        EVIDENCE_VERSION,
        RESPONSE_DATE,
        REDUCED_SURFACE_ONLY,
        lifecycle_policy.POLICY_VERSION,
        gate_mapping.MAPPING_VERSION,
        mapping.status,
        lifecycle_filter.VERSION,
        artifact_integration.VERSION,
        launch_rehearsal.VERSION,
        lifecycle_receipt.LIFECYCLE_RECEIPT_VERSION,
        bounded_runner.RUNNER_VERSION,
        True,
        True,
        False,
        False,
        False,
        False,
    )


def _result(
    status: str,
    *,
    official_pending: bool,
    scope: str = "UNCONFIRMED",
    review_candidate: bool = False,
    full_surface_pending: bool = True,
    lifecycle_pipeline_verified: bool = False,
    source_binding_verified: bool = False,
    d1_reconfirmed: bool = False,
    manual_gate_approved: bool = False,
    next_action: str,
    blockers: tuple[str, ...],
    reasons: tuple[str, ...],
) -> ControlCenterEvidenceSync:
    return ControlCenterEvidenceSync(
        VERSION,
        status,
        official_pending,
        scope,
        review_candidate,
        full_surface_pending,
        lifecycle_pipeline_verified,
        source_binding_verified,
        d1_reconfirmed,
        manual_gate_approved,
        False,
        False,
        False,
        False,
        next_action,
        tuple(sorted(set(blockers))),
        tuple(sorted(set(reasons))),
    )


def synchronize_control_center_evidence(
    evidence: Any,
) -> ControlCenterEvidenceSync:
    """Classify confirmed contracts and missing operational proof separately."""

    try:
        if type(evidence) is not ControlCenterEvidence:
            return _result(
                FAIL_CLOSED,
                official_pending=True,
                next_action="PROVIDE_VERSIONED_CONTROL_CENTER_EVIDENCE",
                blockers=("CONTROL_CENTER_EVIDENCE_REQUIRED",),
                reasons=("CONTROL_CENTER_EVIDENCE_TYPE_INVALID",),
            )
        booleans = (
            evidence.builder_prefilter_verified,
            evidence.saved_receipts_fail_closed_verified,
            evidence.source_db_artifact_binding_verified,
            evidence.production_d1_read_only_reconfirmed,
            evidence.manual_reduced_surface_gate_approved,
            evidence.full_surface_official_confirmation_received,
        )
        if any(type(value) is not bool for value in booleans):
            return _result(
                FAIL_CLOSED,
                official_pending=True,
                next_action="CORRECT_CONTROL_CENTER_EVIDENCE_TYPES",
                blockers=("CONTROL_CENTER_EVIDENCE_MALFORMED",),
                reasons=("CONTROL_CENTER_EVIDENCE_BOOLEAN_INVALID",),
            )
        if evidence.official_response_received_on is None:
            return _result(
                FAIL_CLOSED,
                official_pending=True,
                next_action="INTAKE_VERSIONED_OFFICIAL_RESPONSE_EVIDENCE",
                blockers=("OFFICIAL_RESPONSE_EVIDENCE_REQUIRED",),
                reasons=("OFFICIAL_RESPONSE_NOT_CONFIRMED",),
            )
        expected_versions = (
            EVIDENCE_VERSION,
            RESPONSE_DATE,
            REDUCED_SURFACE_ONLY,
            lifecycle_policy.POLICY_VERSION,
            gate_mapping.MAPPING_VERSION,
            gate_mapping.REVIEW_CANDIDATE,
            lifecycle_filter.VERSION,
            artifact_integration.VERSION,
            launch_rehearsal.VERSION,
            lifecycle_receipt.LIFECYCLE_RECEIPT_VERSION,
            bounded_runner.RUNNER_VERSION,
        )
        actual_versions = (
            evidence.evidence_version,
            evidence.official_response_received_on,
            evidence.official_response_scope,
            evidence.official_policy_version,
            evidence.reduced_surface_mapping_version,
            evidence.reduced_surface_mapping_status,
            evidence.lifecycle_filter_version,
            evidence.artifact_integration_version,
            evidence.launch_rehearsal_version,
            evidence.lifecycle_receipt_version,
            evidence.bounded_runner_version,
        )
        if actual_versions != expected_versions:
            return _result(
                FAIL_CLOSED,
                official_pending=True,
                next_action="RECONCILE_VERSIONED_CONTROL_CENTER_EVIDENCE",
                blockers=("CONTROL_CENTER_EVIDENCE_VERSION_OR_SCOPE_MISMATCH",),
                reasons=("TRACKED_EVIDENCE_CONTRACT_MISMATCH",),
            )
        if evidence.full_surface_official_confirmation_received:
            return _result(
                FAIL_CLOSED,
                official_pending=False,
                scope=REDUCED_SURFACE_ONLY,
                full_surface_pending=True,
                next_action="PROVIDE_VERSIONED_FULL_SURFACE_EVIDENCE",
                blockers=("FULL_SURFACE_EVIDENCE_OUT_OF_SCOPE",),
                reasons=("REDUCED_SURFACE_EVIDENCE_CANNOT_CONFIRM_FULL_SURFACE",),
            )

        lifecycle_pipeline_verified = (
            evidence.builder_prefilter_verified
            and evidence.saved_receipts_fail_closed_verified
        )
        blockers: list[str] = []
        if not lifecycle_pipeline_verified:
            blockers.append("LIFECYCLE_PIPELINE_EVIDENCE_INCOMPLETE")
        if not evidence.source_db_artifact_binding_verified:
            blockers.append("SOURCE_DB_AND_PUBLIC_ARTIFACT_REVALIDATION_REQUIRED")
        if not evidence.production_d1_read_only_reconfirmed:
            blockers.append("PRODUCTION_D1_READ_ONLY_RECONFIRMATION_REQUIRED")
        if not evidence.manual_reduced_surface_gate_approved:
            blockers.append("REDUCED_SURFACE_MANUAL_GATE_REVIEW_REQUIRED")

        if "LIFECYCLE_PIPELINE_EVIDENCE_INCOMPLETE" in blockers:
            next_action = "COMPLETE_LIFECYCLE_PIPELINE_EVIDENCE_REVIEW"
        elif "SOURCE_DB_AND_PUBLIC_ARTIFACT_REVALIDATION_REQUIRED" in blockers:
            next_action = "REVALIDATE_SOURCE_DB_AND_PUBLIC_ARTIFACT"
        elif "PRODUCTION_D1_READ_ONLY_RECONFIRMATION_REQUIRED" in blockers:
            next_action = "RECONFIRM_PRODUCTION_D1_READ_ONLY"
        elif "REDUCED_SURFACE_MANUAL_GATE_REVIEW_REQUIRED" in blockers:
            next_action = "REVIEW_REDUCED_SURFACE_GATE_MANUALLY"
        else:
            next_action = "REVIEW_SEPARATE_PUBLICATION_GATE"

        status = SYNCED_BLOCKED if blockers else REVIEW_CANDIDATE
        reasons = [
            "OFFICIAL_RESPONSE_REFLECTED_FOR_REDUCED_SURFACE_ONLY",
            "TRACKED_LIFECYCLE_CONTRACTS_VERSION_BOUND",
            "PUBLICATION_AND_PRODUCTION_REMAIN_CLOSED",
        ]
        reasons.append("FULL_SURFACE_OFFICIAL_CONFIRMATION_STILL_PENDING")
        return _result(
            status,
            official_pending=False,
            scope=REDUCED_SURFACE_ONLY,
            review_candidate=True,
            full_surface_pending=True,
            lifecycle_pipeline_verified=lifecycle_pipeline_verified,
            source_binding_verified=(
                evidence.source_db_artifact_binding_verified
            ),
            d1_reconfirmed=evidence.production_d1_read_only_reconfirmed,
            manual_gate_approved=evidence.manual_reduced_surface_gate_approved,
            next_action=next_action,
            blockers=tuple(blockers),
            reasons=tuple(reasons),
        )
    except Exception:
        return _result(
            FAIL_CLOSED,
            official_pending=True,
            next_action="RECONCILE_CONTROL_CENTER_EVIDENCE",
            blockers=("CONTROL_CENTER_EVIDENCE_INTERNAL_ERROR",),
            reasons=("CONTROL_CENTER_EVIDENCE_SYNC_FAILED",),
        )


def current_sync() -> ControlCenterEvidenceSync:
    return synchronize_control_center_evidence(current_tracked_evidence())


def main() -> int:
    result = current_sync()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == REVIEW_CANDIDATE else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ControlCenterEvidence",
    "ControlCenterEvidenceSync",
    "EVIDENCE_VERSION",
    "FAIL_CLOSED",
    "REDUCED_SURFACE_ONLY",
    "RESPONSE_DATE",
    "REVIEW_CANDIDATE",
    "SYNCED_BLOCKED",
    "VERSION",
    "current_sync",
    "current_tracked_evidence",
    "synchronize_control_center_evidence",
]
