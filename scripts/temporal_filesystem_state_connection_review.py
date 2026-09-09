"""Pure evidence review for the first post-dry temporal connection Gate."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import json
from typing import Any


VERSION = "0.1-candidate"
SELECTED_TARGET = "FILESYSTEM_BACKED_STATE"
REVIEW_BLOCKED = "REVIEW_BLOCKED"
REVIEW_READY_FOR_EXPLICIT_APPROVAL = "REVIEW_READY_FOR_EXPLICIT_APPROVAL"
REVIEW_AREAS = (
    "PREREQUISITES",
    "TRUST_BOUNDARY",
    "ROLLBACK_RECOVERY",
    "SECRET_PII",
    "IDEMPOTENCY",
    "RATE_COST",
    "PUBLICATION_COMPLIANCE",
    "EXPLICIT_APPROVAL_POINT",
)


@dataclass(frozen=True)
class FilesystemStateConnectionEvidence:
    version: str
    selected_target: str
    prerequisites_verified: bool
    trust_boundary_verified: bool
    rollback_recovery_verified: bool
    secret_pii_controls_verified: bool
    idempotency_verified: bool
    rate_cost_bounds_verified: bool
    publication_compliance_separation_verified: bool
    explicit_approval_point_defined: bool
    explicit_approval_granted: bool


@dataclass(frozen=True)
class FilesystemStateConnectionReview:
    version: str
    status: str
    selected_target: str
    review_areas: tuple[str, ...]
    unmet_areas: tuple[str, ...]
    connection_authorized: bool
    write_authorized: bool
    deploy_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["review_areas"] = list(self.review_areas)
        value["unmet_areas"] = list(self.unmet_areas)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(code: str, unmet: tuple[str, ...] = REVIEW_AREAS) -> FilesystemStateConnectionReview:
    return FilesystemStateConnectionReview(
        VERSION, REVIEW_BLOCKED, SELECTED_TARGET, REVIEW_AREAS, unmet,
        False, False, False, (code,),
    )


def review_filesystem_state_connection(evidence: Any) -> FilesystemStateConnectionReview:
    """Review caller-supplied facts without filesystem, network, or target calls."""

    try:
        if type(evidence) is not FilesystemStateConnectionEvidence:
            return _blocked("EVIDENCE_TYPE_INVALID")
        if tuple(evidence.__dataclass_fields__) != tuple(
            field.name for field in fields(FilesystemStateConnectionEvidence)
        ):
            return _blocked("EVIDENCE_SCHEMA_INVALID")
        if evidence.version != VERSION or evidence.selected_target != SELECTED_TARGET:
            return _blocked("EVIDENCE_IDENTITY_INVALID")

        boolean_values = tuple(
            getattr(evidence, field.name)
            for field in fields(FilesystemStateConnectionEvidence)
            if field.name not in {"version", "selected_target"}
        )
        if any(type(value) is not bool for value in boolean_values):
            return _blocked("EVIDENCE_BOOLEAN_INVALID")
        if evidence.explicit_approval_granted:
            return _blocked("APPROVAL_INPUT_NOT_ACCEPTED")

        checks = (
            evidence.prerequisites_verified,
            evidence.trust_boundary_verified,
            evidence.rollback_recovery_verified,
            evidence.secret_pii_controls_verified,
            evidence.idempotency_verified,
            evidence.rate_cost_bounds_verified,
            evidence.publication_compliance_separation_verified,
            evidence.explicit_approval_point_defined,
        )
        unmet = tuple(area for area, complete in zip(REVIEW_AREAS, checks) if not complete)
        if unmet:
            return _blocked("REVIEW_EVIDENCE_INCOMPLETE", unmet)
        return FilesystemStateConnectionReview(
            VERSION, REVIEW_READY_FOR_EXPLICIT_APPROVAL, SELECTED_TARGET,
            REVIEW_AREAS, (), False, False, False,
            ("FILESYSTEM_STATE_REVIEW_COMPLETE", "EXPLICIT_APPROVAL_REQUIRED"),
        )
    except Exception:
        return _blocked("REVIEW_EVALUATION_ERROR")


def main() -> int:
    result = _blocked("CALLER_EVIDENCE_REQUIRED")
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
