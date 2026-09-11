"""Pure review boundary for the isolated temporal persistence candidate."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any


VERSION = "0.1-candidate"
REVIEW_BLOCKED = "REVIEW_BLOCKED"
REVIEW_READY_FOR_EXPLICIT_APPROVAL = "REVIEW_READY_FOR_EXPLICIT_APPROVAL"
REVIEW_AREAS = (
    "TEST_ONLY_CONSTRUCTION",
    "OWNED_ROOT_CONFINEMENT",
    "PLAN_DOCUMENT_VALIDATION",
    "ATOMIC_WRITE_EXACT_READBACK",
    "REPLAY_COLLISION_HANDLING",
    "UNCERTAIN_RESULT_RECOVERY",
    "SIZE_FREQUENCY_BOUNDS",
    "RESULT_REDACTION",
    "ACTIVE_FLOW_SEPARATION",
)


@dataclass(frozen=True)
class PersistenceCandidateEvidence:
    version: str
    test_only_construction_verified: bool
    owned_root_confinement_verified: bool
    plan_document_validation_verified: bool
    atomic_write_exact_readback_verified: bool
    replay_collision_handling_verified: bool
    uncertain_result_recovery_verified: bool
    size_frequency_bounds_verified: bool
    result_redaction_verified: bool
    active_flow_separation_verified: bool
    explicit_approval_granted: bool


@dataclass(frozen=True)
class PersistenceCandidateReview:
    version: str
    status: str
    review_areas: tuple[str, ...]
    unmet_areas: tuple[str, ...]
    filesystem_connection_authorized: bool
    production_write_authorized: bool
    deploy_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["review_areas"] = list(self.review_areas)
        value["unmet_areas"] = list(self.unmet_areas)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(code: str, unmet: tuple[str, ...] = REVIEW_AREAS) -> PersistenceCandidateReview:
    return PersistenceCandidateReview(
        VERSION, REVIEW_BLOCKED, REVIEW_AREAS, unmet,
        False, False, False, (code,),
    )


def review_persistence_candidate(value: Any) -> PersistenceCandidateReview:
    """Review caller-supplied booleans without performing filesystem access."""
    try:
        if type(value) is not PersistenceCandidateEvidence:
            return _blocked("EVIDENCE_TYPE_INVALID")
        if tuple(value.__dataclass_fields__) != tuple(
            field.name for field in fields(PersistenceCandidateEvidence)
        ):
            return _blocked("EVIDENCE_SCHEMA_INVALID")
        if value.version != VERSION:
            return _blocked("EVIDENCE_VERSION_INVALID")
        checks = tuple(
            getattr(value, field.name)
            for field in fields(PersistenceCandidateEvidence)
            if field.name not in {"version", "explicit_approval_granted"}
        )
        if any(type(item) is not bool for item in checks) or type(
            value.explicit_approval_granted
        ) is not bool:
            return _blocked("EVIDENCE_BOOLEAN_INVALID")
        if value.explicit_approval_granted:
            return _blocked("APPROVAL_INPUT_NOT_ACCEPTED")
        unmet = tuple(area for area, complete in zip(REVIEW_AREAS, checks) if not complete)
        if unmet:
            return _blocked("REVIEW_EVIDENCE_INCOMPLETE", unmet)
        return PersistenceCandidateReview(
            VERSION, REVIEW_READY_FOR_EXPLICIT_APPROVAL, REVIEW_AREAS, (),
            False, False, False,
            ("TEST_ONLY_PERSISTENCE_EVIDENCE_REVIEWED", "EXPLICIT_CONNECTION_APPROVAL_REQUIRED"),
        )
    except Exception:
        return _blocked("REVIEW_EVALUATION_ERROR")


__all__ = [
    "PersistenceCandidateEvidence", "PersistenceCandidateReview", "REVIEW_AREAS",
    "REVIEW_BLOCKED", "REVIEW_READY_FOR_EXPLICIT_APPROVAL", "VERSION",
    "review_persistence_candidate",
]
