"""Pure registry for official-confirmation and publication blockers."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
import re
from typing import Any


POLICY_VERSION = "0.1"
BLOCKER_VERSION = "0.1"

PENDING_OFFICIAL_CONFIRMATION = "PENDING_OFFICIAL_CONFIRMATION"
PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
RESOLVED = "RESOLVED"
NOT_APPLICABLE = "NOT_APPLICABLE"
INTERNAL_APPROVAL_REQUIRED = "INTERNAL_APPROVAL_REQUIRED"
BLOCKER_STATES = frozenset({
    PENDING_OFFICIAL_CONFIRMATION, PARTIALLY_RESOLVED, RESOLVED,
    NOT_APPLICABLE, INTERNAL_APPROVAL_REQUIRED,
})

DIRECT_SUPPORT_CONFIRMATION = "DIRECT_SUPPORT_CONFIRMATION"
OFFICIAL_DOCUMENTATION = "OFFICIAL_DOCUMENTATION"
INTERNAL_VALIDATION = "INTERNAL_VALIDATION"
NO_VALID_EVIDENCE = "NO_VALID_EVIDENCE"
EVIDENCE_TYPES = frozenset({
    DIRECT_SUPPORT_CONFIRMATION, OFFICIAL_DOCUMENTATION,
    INTERNAL_VALIDATION, NO_VALID_EVIDENCE,
})
OFFICIAL_EVIDENCE = frozenset({DIRECT_SUPPORT_CONFIRMATION, OFFICIAL_DOCUMENTATION})

LIFECYCLE_BLOCKER = "DMM_LIFECYCLE_AVAILABILITY"
SORT_BLOCKER = "DMM_SORT_SEMANTICS"
PUBLICATION_BLOCKER = "PUBLICATION_ACTIVATION"
BLOCKER_IDS = (LIFECYCLE_BLOCKER, SORT_BLOCKER, PUBLICATION_BLOCKER)

FORBIDDEN_INFERENCES = frozenset({
    "ZERO_RESULT_MEANS_SALE_ENDED",
    "AFFILIATE_URL_ABSENT_MEANS_INELIGIBLE",
    "API_VISIBLE_MEANS_PURCHASABLE",
    "API_INVISIBLE_MEANS_DELETED",
    "NOT_OBSERVED_FOR_DAYS_MEANS_UNAVAILABLE",
})


@dataclass(frozen=True)
class BlockerRecord:
    blocker_id: str
    blocker_version: str
    status: str
    affected_gate: str
    unresolved_questions: tuple[str, ...]
    resolution_requirements: tuple[str, ...]
    evidence_type: str
    evidence_date: str | None
    evidence_reference: str | None
    safe_notes: tuple[str, ...]
    gate_unlock_allowed: bool

    def safe_dict(self) -> dict[str, Any]:
        """Return bounded metadata without questions, raw evidence, paths, or mail."""
        return {
            "blocker_id": self.blocker_id,
            "blocker_version": self.blocker_version,
            "status": self.status,
            "affected_gate": self.affected_gate,
            "evidence_type": self.evidence_type,
            "evidence_date": self.evidence_date,
            "evidence_reference": self.evidence_reference,
            "safe_notes": list(self.safe_notes),
            "gate_unlock_allowed": self.gate_unlock_allowed,
        }


def _record(blocker_id: str, status: str, gate: str, questions: tuple[str, ...], requirements: tuple[str, ...], evidence: str, notes: tuple[str, ...]) -> BlockerRecord:
    return BlockerRecord(
        blocker_id, BLOCKER_VERSION, status, gate, questions, requirements,
        evidence, None, None, notes, False,
    )


_LIFECYCLE_QUESTIONS = (
    "CID ItemList zero-result meaning",
    "sale ended / unpublished / deleted / affiliate ineligible distinction",
    "temporary API visibility distinction",
    "affiliateURL presence or absence meaning",
    "recommended periodic CID re-query operation",
    "history display after API invisibility",
    "affiliate link removal condition",
    "official lifecycle signals",
)
_LIFECYCLE_REQUIREMENTS = (
    "ItemList/CID availability interpretation",
    "zero-result conversion rule",
    "affiliateURL eligibility interpretation",
    "periodic re-query guidance",
    "public page and affiliate link handling after API invisibility",
)
_SORT_QUESTIONS = (
    "official sort=rank definition", "official sort=review definition",
    "rank and review ordering criteria", "offset/source_position meaning",
    "whether query response position may be a public rank claim",
    "rank/review update behavior over time",
)
_SORT_REQUIREMENTS = (
    "official sort=rank definition", "official sort=review definition",
    "position/offset interpretation", "permitted public wording",
)
_PUBLICATION_REQUIREMENTS = (
    "Rights Gate PASS", "Lifecycle Gate PASS", "required Semantics Gate PASS",
    "Data Policy Gate PASS", "public artifact validation PASS",
    "production build PASS", "deployment preflight PASS",
    "separate commit and explicit internal approval",
)

_RECORDS = (
    _record(
        LIFECYCLE_BLOCKER, PENDING_OFFICIAL_CONFIRMATION, "LIFECYCLE_GATE",
        _LIFECYCLE_QUESTIONS, _LIFECYCLE_REQUIREMENTS, NO_VALID_EVIDENCE,
        ("No availability state may be inferred from current API observations.",),
    ),
    _record(
        SORT_BLOCKER, PENDING_OFFICIAL_CONFIRMATION, "SEMANTICS_GATE",
        _SORT_QUESTIONS, _SORT_REQUIREMENTS, NO_VALID_EVIDENCE,
        ("Only rank-sorted population, review-sorted population, and query response position are safe before confirmation.",),
    ),
    _record(
        PUBLICATION_BLOCKER, INTERNAL_APPROVAL_REQUIRED, "PUBLICATION_STATUS_GATE",
        (), _PUBLICATION_REQUIREMENTS, INTERNAL_VALIDATION,
        ("Publication activation is manual and must occur in a separate approved commit.",),
    ),
)

BLOCKERS = MappingProxyType({record.blocker_id: record for record in _RECORDS})


def blocker_for(blocker_id: str) -> BlockerRecord:
    if not isinstance(blocker_id, str) or blocker_id not in BLOCKERS:
        raise KeyError("UNKNOWN_BLOCKER")
    return BLOCKERS[blocker_id]


def inference_allowed(inference: str) -> bool:
    if not isinstance(inference, str) or inference not in FORBIDDEN_INFERENCES:
        raise KeyError("UNKNOWN_INFERENCE")
    return False


_UNSAFE_REFERENCE = re.compile(
    r"(?i)(?:api|affiliate)[_-]?id\s*[:=]|(?:password|secret|token)\s*[:=]|"
    r"(?:[a-z]:[\\/]|/home/|/users/)|\r|\n"
)


def evidence_reference_is_safe(value: Any) -> bool:
    return value is None or (
        isinstance(value, str)
        and 0 < len(value) <= 200
        and _UNSAFE_REFERENCE.search(value) is None
    )


def resolution_unlock_allowed(record: Any) -> bool:
    """Assess a proposed record; never mutate the current registry."""
    if not isinstance(record, BlockerRecord):
        return False
    if record.blocker_id not in BLOCKERS or record.blocker_version != BLOCKER_VERSION:
        return False
    if record.status not in BLOCKER_STATES or record.evidence_type not in EVIDENCE_TYPES:
        return False
    if not isinstance(record.gate_unlock_allowed, bool):
        return False
    if not evidence_reference_is_safe(record.evidence_reference):
        return False
    if record.blocker_id == PUBLICATION_BLOCKER:
        return False
    return (
        record.status == RESOLVED
        and record.evidence_type in OFFICIAL_EVIDENCE
        and not record.unresolved_questions
        and record.gate_unlock_allowed
    )


def semantics_gate_unlock_allowed(rank_status: str, review_status: str, evidence_type: str) -> bool:
    if rank_status not in BLOCKER_STATES or review_status not in BLOCKER_STATES:
        return False
    return rank_status == review_status == RESOLVED and evidence_type in OFFICIAL_EVIDENCE


def publication_activation_allowed(required_gate_statuses: dict[str, str], *, explicit_internal_approval: bool) -> bool:
    required = {"RIGHTS_GATE", "LIFECYCLE_GATE", "SEMANTICS_GATE", "DATA_POLICY_GATE", "ARTIFACT_VALIDATION", "PRODUCTION_BUILD", "DEPLOYMENT_PREFLIGHT"}
    return (
        isinstance(required_gate_statuses, dict)
        and set(required_gate_statuses) == required
        and all(value == "PASS" for value in required_gate_statuses.values())
        and explicit_internal_approval is True
    )


def validate_registry() -> tuple[str, ...]:
    errors: list[str] = []
    if POLICY_VERSION != "0.1" or BLOCKER_VERSION != "0.1": errors.append("VERSION_INVALID")
    if tuple(BLOCKERS) != BLOCKER_IDS or len(BLOCKERS) != len(_RECORDS): errors.append("BLOCKER_IDS_INVALID")
    for record in _RECORDS:
        if record.status not in BLOCKER_STATES: errors.append("UNKNOWN_STATE")
        if record.evidence_type not in EVIDENCE_TYPES: errors.append("UNKNOWN_EVIDENCE")
        if record.gate_unlock_allowed: errors.append("CURRENT_UNLOCK_FORBIDDEN")
        if not evidence_reference_is_safe(record.evidence_reference): errors.append("UNSAFE_REFERENCE")
    return tuple(sorted(set(errors)))


def safe_registry_result() -> dict[str, Any]:
    return {"registry_version": POLICY_VERSION, "blockers": [BLOCKERS[value].safe_dict() for value in BLOCKER_IDS]}


__all__ = [
    "BLOCKER_IDS", "BLOCKERS", "BLOCKER_STATES", "BLOCKER_VERSION",
    "BlockerRecord", "DIRECT_SUPPORT_CONFIRMATION", "EVIDENCE_TYPES",
    "FORBIDDEN_INFERENCES", "INTERNAL_APPROVAL_REQUIRED", "INTERNAL_VALIDATION",
    "LIFECYCLE_BLOCKER", "NO_VALID_EVIDENCE", "NOT_APPLICABLE",
    "OFFICIAL_DOCUMENTATION", "PARTIALLY_RESOLVED", "PENDING_OFFICIAL_CONFIRMATION",
    "POLICY_VERSION", "PUBLICATION_BLOCKER", "RESOLVED", "SORT_BLOCKER",
    "blocker_for", "evidence_reference_is_safe", "inference_allowed",
    "publication_activation_allowed", "resolution_unlock_allowed",
    "safe_registry_result", "semantics_gate_unlock_allowed", "validate_registry",
]
