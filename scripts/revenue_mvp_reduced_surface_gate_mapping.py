"""Pure versioned mapping from merged P0 evidence to reduced-surface review."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import official_blocker_policy as blockers
import publication_readiness as readiness
import revenue_mvp_official_lifecycle_policy as lifecycle
import revenue_mvp_offline_artifact_integration as artifact
import revenue_mvp_offline_launch_rehearsal as rehearsal
import revenue_mvp_offline_lifecycle_filter as lifecycle_filter
import revenue_mvp_reduced_surface_semantics as surface


MAPPING_VERSION = "0.1-candidate"
REVIEW_CANDIDATE = "REDUCED_SURFACE_REVIEW_CANDIDATE"
BLOCKED = "REDUCED_SURFACE_BLOCKED"
FAIL_CLOSED = "REDUCED_SURFACE_FAIL_CLOSED"
OUT_OF_SCOPE = "OUT_OF_SCOPE_FOR_REDUCED_SURFACE"
REQUIRED = "REQUIRED_FOR_REDUCED_SURFACE"
SATISFIED = "SATISFIED_FOR_REDUCED_SURFACE_REVIEW"

REQUIRED_SEMANTICS = (
    "API_UNAVAILABLE_EXCLUSION",
    "AFFILIATE_URL_REQUIRED",
    "ERROR_RATE_LIMIT_STALE_EXCLUSION",
    "PREORDER_STOCK_NOT_SOLE_EXCLUSION",
    "API_ORDER_LABEL_GUARD",
    "OBSERVATION_TIMESTAMP_PROVENANCE",
    "CTA_SAME_ITEM_OBSERVATION_PR_GATE",
    "INDEX_DETAIL_ATOMIC_FILTER",
    "OFFLINE_ROLLBACK",
)
OUT_OF_SCOPE_SEMANTICS = (
    "ORDINAL_PUBLIC_RANK",
    "PROVIDER_UPDATE_BEHAVIOR",
    "INTERNAL_HISTORY_RETENTION",
)


@dataclass(frozen=True)
class ReducedSurfaceGateEvidence:
    mapping_version: str
    blocker_policy_version: str
    publication_readiness_version: str
    lifecycle_policy_version: str
    reduced_surface_contract_version: str
    lifecycle_filter_version: str
    artifact_integration_version: str
    launch_rehearsal_version: str
    lifecycle_policy_verified: bool
    reduced_surface_contract_verified: bool
    lifecycle_filter_verified: bool
    artifact_integration_verified: bool
    launch_rehearsal_verified: bool


@dataclass(frozen=True)
class ReducedSurfaceGateMappingReview:
    mapping_version: str
    status: str
    surface_scope: str
    required_semantics: tuple[dict[str, str], ...]
    out_of_scope_semantics: tuple[dict[str, str], ...]
    existing_blocker_statuses: tuple[dict[str, str], ...]
    full_surface_status: str
    expanded_surface_status: str
    publication_readiness_status: str
    publication_status: str
    gate_mutation_allowed: bool
    production_allowed: bool
    affiliate_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["required_semantics"] = list(self.required_semantics)
        value["out_of_scope_semantics"] = list(self.out_of_scope_semantics)
        value["existing_blocker_statuses"] = list(self.existing_blocker_statuses)
        value["reason_codes"] = list(self.reason_codes)
        return value


def current_versioned_evidence() -> ReducedSurfaceGateEvidence:
    """Return version bindings only; it performs no evidence execution."""

    return ReducedSurfaceGateEvidence(
        MAPPING_VERSION,
        blockers.POLICY_VERSION,
        readiness.REPORT_VERSION,
        lifecycle.POLICY_VERSION,
        surface.CONTRACT_VERSION,
        lifecycle_filter.VERSION,
        artifact.VERSION,
        rehearsal.VERSION,
        True,
        True,
        True,
        True,
        True,
    )


def _review(status: str, reasons: tuple[str, ...]) -> ReducedSurfaceGateMappingReview:
    satisfied = status == REVIEW_CANDIDATE
    return ReducedSurfaceGateMappingReview(
        MAPPING_VERSION,
        status,
        "REDUCED_SURFACE",
        tuple({"semantic": value, "status": SATISFIED if satisfied else REQUIRED}
              for value in REQUIRED_SEMANTICS),
        tuple({"semantic": value, "status": OUT_OF_SCOPE}
              for value in OUT_OF_SCOPE_SEMANTICS),
        tuple({
            "blocker_id": blocker_id,
            "status": blockers.BLOCKERS[blocker_id].status,
        } for blocker_id in blockers.BLOCKER_IDS),
        blockers.PENDING_OFFICIAL_CONFIRMATION,
        blockers.PENDING_OFFICIAL_CONFIRMATION,
        readiness.BLOCKED,
        "CLOSED",
        False,
        False,
        False,
        reasons,
    )


def review_reduced_surface_gate_mapping(
    evidence: Any,
) -> ReducedSurfaceGateMappingReview:
    """Assess a separate review candidate without mutating Registry or Gates."""

    try:
        if type(evidence) is not ReducedSurfaceGateEvidence:
            return _review(FAIL_CLOSED, ("EVIDENCE_TYPE_INVALID",))
        expected_versions = (
            MAPPING_VERSION,
            blockers.POLICY_VERSION,
            readiness.REPORT_VERSION,
            lifecycle.POLICY_VERSION,
            surface.CONTRACT_VERSION,
            lifecycle_filter.VERSION,
            artifact.VERSION,
            rehearsal.VERSION,
        )
        actual_versions = (
            evidence.mapping_version,
            evidence.blocker_policy_version,
            evidence.publication_readiness_version,
            evidence.lifecycle_policy_version,
            evidence.reduced_surface_contract_version,
            evidence.lifecycle_filter_version,
            evidence.artifact_integration_version,
            evidence.launch_rehearsal_version,
        )
        if actual_versions != expected_versions:
            return _review(FAIL_CLOSED, ("EVIDENCE_VERSION_MISMATCH",))
        verified = (
            evidence.lifecycle_policy_verified,
            evidence.reduced_surface_contract_verified,
            evidence.lifecycle_filter_verified,
            evidence.artifact_integration_verified,
            evidence.launch_rehearsal_verified,
        )
        if any(type(value) is not bool for value in verified):
            return _review(FAIL_CLOSED, ("EVIDENCE_BOOLEAN_INVALID",))
        if not all(verified):
            return _review(BLOCKED, ("REQUIRED_VERSIONED_EVIDENCE_INCOMPLETE",))

        current = readiness.current_input()
        expected_gates = {
            "RIGHTS_GATE": "PASS",
            "DATA_POLICY_GATE": "PASS",
            "LIFECYCLE_GATE": blockers.PENDING_OFFICIAL_CONFIRMATION,
            "SEMANTICS_GATE": blockers.PENDING_OFFICIAL_CONFIRMATION,
            "PUBLICATION_STATUS_GATE": "CLOSED",
        }
        if (
            blockers.validate_registry() != ()
            or current.gates != expected_gates
            or current.overall_eligible is not False
            or current.publication_status != "local_validation_only"
            or any(record.gate_unlock_allowed for record in blockers.BLOCKERS.values())
        ):
            return _review(FAIL_CLOSED, ("EXISTING_GATE_BOUNDARY_CHANGED",))
        return _review(
            REVIEW_CANDIDATE,
            (
                "REDUCED_SURFACE_REQUIRED_SEMANTICS_MAPPED",
                "EXISTING_REGISTRY_UNCHANGED",
                "FULL_AND_EXPANDED_SURFACES_REMAIN_BLOCKED",
                "SEPARATE_GATE_REVIEW_REQUIRED",
            ),
        )
    except Exception:
        return _review(FAIL_CLOSED, ("GATE_MAPPING_REVIEW_ERROR",))


__all__ = [
    "BLOCKED", "FAIL_CLOSED", "MAPPING_VERSION", "OUT_OF_SCOPE",
    "OUT_OF_SCOPE_SEMANTICS", "REQUIRED_SEMANTICS", "REVIEW_CANDIDATE",
    "ReducedSurfaceGateEvidence", "ReducedSurfaceGateMappingReview",
    "current_versioned_evidence", "review_reduced_surface_gate_mapping",
]
