"""Audit reusable prior evidence for doujin questions without resolving scope."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import doujin_compliance_questionnaire as questionnaire
import revenue_mvp_official_answer_matrix as answer_matrix
import revenue_mvp_scoped_one_cta_gates as cta_policy
import rights_decision_policy as rights


VERSION = "0.1"
READY = "READY_FOR_PRIOR_EVIDENCE_SCOPE_REVIEW"
FAIL_CLOSED = "FAIL_CLOSED"

SCOPE_REVIEW_CANDIDATES = tuple(
    row.question_id for row in questionnaire.QUESTIONS
    if row.owner == questionnaire.DMM_SUPPORT and row.prior_evidence_candidate
)
RECONTACT_REQUIRED = tuple(
    row.question_id for row in questionnaire.QUESTIONS
    if row.owner == questionnaire.DMM_SUPPORT and not row.prior_evidence_candidate
)
INTERNAL_REVIEW = tuple(
    row.question_id for row in questionnaire.QUESTIONS
    if row.owner == questionnaire.INTERNAL
)
RETENTION_SCOPE_AMBIGUITY = (
    "SANITIZED_RAW_RETENTION_ALLOWED",
    "SANITIZED_RAW_RETENTION_DURATION",
    "HISTORICAL_NORMALIZED_PRICE_RETENTION",
)


@dataclass(frozen=True)
class PriorEvidenceReuseAudit:
    version: str
    status: str
    scope_review_candidate_ids: tuple[str, ...]
    recontact_required_ids: tuple[str, ...]
    internal_review_ids: tuple[str, ...]
    retention_scope_ambiguity_ids: tuple[str, ...]
    resolved_without_review_ids: tuple[str, ...]
    external_send_performed: bool
    compliance_approved: bool
    publication_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in (
            "scope_review_candidate_ids", "recontact_required_ids",
            "internal_review_ids", "retention_scope_ambiguity_ids",
            "resolved_without_review_ids", "reason_codes",
        ):
            value[key] = list(value[key])
        return value


def _failed(reason: str) -> PriorEvidenceReuseAudit:
    return PriorEvidenceReuseAudit(
        VERSION, FAIL_CLOSED, (), (), (), (), (), False, False, False, (reason,)
    )


def assess() -> PriorEvidenceReuseAudit:
    try:
        questions = questionnaire.build()
        if questions.status != "READY_FOR_MANUAL_REVIEW":
            return _failed("QUESTIONNAIRE_NOT_READY")
        entries = answer_matrix.current_entries()
        required_topics = (
            "API_HISTORY_DISPLAY", "RETENTION_UPDATE_DELETION", "API_IMAGE_USE",
            "DISCONTINUED_ITEM_HANDLING",
        )
        if any(topic not in entries for topic in required_topics):
            return _failed("PRIOR_ANSWER_TOPIC_MISSING")
        if entries["API_HISTORY_DISPLAY"].status != answer_matrix.ALLOWED:
            return _failed("HISTORY_EVIDENCE_DRIFT")
        if entries["RETENTION_UPDATE_DELETION"].status != answer_matrix.ALLOWED:
            return _failed("RETENTION_EVIDENCE_DRIFT")
        for topic in ("API_IMAGE_USE", "DISCONTINUED_ITEM_HANDLING"):
            decision = entries[topic]
            if (
                decision.status != answer_matrix.CONDITIONALLY_ALLOWED
                or not decision.conditions_verified
            ):
                return _failed("CONDITIONAL_EVIDENCE_DRIFT")
        if rights.validate_policy():
            return _failed("RIGHTS_POLICY_INVALID")
        for field in ("price", "product_main_image", "product_page_url"):
            decision = rights.decision_for(field)
            if (
                decision.public_display != rights.APPROVED
                or decision.evidence_type != rights.DIRECT_SUPPORT_CONFIRMATION
            ):
                return _failed("RIGHTS_EVIDENCE_DRIFT")
        if cta_policy.OFFICIAL_STATUS != "LINK_ALLOWED_RELAY_DISCOURAGED_UNGUARANTEED":
            return _failed("LINK_EVIDENCE_DRIFT")
        routed = set(SCOPE_REVIEW_CANDIDATES) | set(RECONTACT_REQUIRED) | set(INTERNAL_REVIEW)
        if routed != set(questionnaire.QUESTION_IDS):
            return _failed("QUESTION_ROUTING_INCOMPLETE")
        return PriorEvidenceReuseAudit(
            VERSION, READY, SCOPE_REVIEW_CANDIDATES, RECONTACT_REQUIRED,
            INTERNAL_REVIEW, RETENTION_SCOPE_AMBIGUITY, (), False, False, False,
            (
                "PRIOR_EVIDENCE_REQUIRES_EXACT_DOUJIN_SCOPE_REVIEW",
                "RETENTION_SCOPE_NOT_INFERRED",
                "NO_QUESTION_AUTO_RESOLVED",
                "NO_EXTERNAL_SEND",
                "PUBLICATION_REMAINS_CLOSED",
            ),
        )
    except Exception:
        return _failed("PRIOR_EVIDENCE_REUSE_AUDIT_ERROR")


if __name__ == "__main__":
    import json

    result = assess()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    raise SystemExit(0 if result.status == READY else 2)
