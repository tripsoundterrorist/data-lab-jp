"""Inert, exact-scope CTA and one-row D1 review preflights.

Trusted anchors must be supplied by a separately reviewed evidence loader. No
loader or production executor is provided here; a READY result never unlocks
publication, eligibility, redirects, or a database write.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Any


VERSION = "0.1-review-only"
READY = "SCOPED_ONE_CTA_REVIEW_READY"
BLOCKED = "SCOPED_ONE_CTA_BLOCKED"
DELTA_READY = "EXACT_ONE_ROW_DELTA_REVIEW_READY"
DELTA_BLOCKED = "EXACT_ONE_ROW_DELTA_BLOCKED"
OFFICIAL_STATUS = "LINK_ALLOWED_RELAY_DISCOURAGED_UNGUARANTEED"
SHA = re.compile(r"[0-9a-f]{64}\Z")
PUBLIC_ID = re.compile(r"itm_[0-9a-f]{24}\Z")
MAX_AGE = timedelta(hours=24)

EVIDENCE_FIELDS = frozenset({
    "official_response_sha256", "official_response_status", "artifact_sha256",
    "candidate_sha256", "source_sha256", "surface", "route_prefix",
    "public_id", "cta_count", "item_count", "observed_at", "valid_until",
    "compliance_approval_sha256", "compliance_candidate_sha256",
    "user_approval_sha256", "user_candidate_sha256", "free_confirmed_at",
    "rollback_pages_sha256", "rollback_worker_version",
})
ANCHOR_FIELDS = frozenset({
    "official_response_sha256", "artifact_sha256", "candidate_sha256",
    "source_sha256", "public_id", "compliance_approval_sha256",
    "user_approval_sha256", "rollback_pages_sha256", "rollback_worker_version",
    "trusted_review_confirmed",
})
DELTA_FIELDS = frozenset({
    "candidate_sha256", "public_id", "before_total", "before_enabled",
    "before_eligible", "matched_row_count", "affected_row_count",
    "after_total", "after_enabled", "after_eligible", "eligible_id_matches",
})


@dataclass(frozen=True)
class Decision:
    version: str
    status: str
    review_ready: bool
    production_activation_allowed: bool = False
    publication_allowed: bool = False
    affiliate_eligibility_allowed: bool = False
    gate_mutation_allowed: bool = False
    d1_write_allowed: bool = False
    route_activation_allowed: bool = False
    api_request_allowed: bool = False
    route_smoke_required: bool = True
    outcome_verification_required: bool = True
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["reason_codes"] = list(self.reason_codes)
        return result


def _decision(status: str, ready: bool, reason: str) -> Decision:
    return Decision(VERSION, status, ready, reason_codes=(reason,))


def _timestamp(value: Any) -> datetime:
    if type(value) is not str:
        raise ValueError("timestamp type")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("naive timestamp")
    return parsed.astimezone(timezone.utc)


def _digest(value: Any) -> bool:
    return type(value) is str and SHA.fullmatch(value) is not None


def evaluate_cta(evidence: Any, anchors: Any, *, now: Any) -> Decision:
    """Assess exact offline evidence; never treat relay permission as success."""
    try:
        if (type(evidence) is not dict or set(evidence) != EVIDENCE_FIELDS
                or type(anchors) is not dict or set(anchors) != ANCHOR_FIELDS
                or type(now) is not datetime or now.tzinfo is None):
            return _decision(BLOCKED, False, "INPUT_CONTRACT_INVALID")
        if anchors["trusted_review_confirmed"] is not True:
            return _decision(BLOCKED, False, "TRUSTED_REVIEW_REQUIRED")
        digest_fields = (
            "official_response_sha256", "artifact_sha256", "candidate_sha256",
            "source_sha256", "compliance_approval_sha256", "user_approval_sha256",
            "rollback_pages_sha256",
        )
        if any(not _digest(evidence[field]) or not _digest(anchors[field])
               or evidence[field] != anchors[field] for field in digest_fields):
            return _decision(BLOCKED, False, "EXACT_EVIDENCE_SHA_MISMATCH")
        if evidence["official_response_status"] != OFFICIAL_STATUS:
            return _decision(BLOCKED, False, "OFFICIAL_CTA_SCOPE_NOT_CONFIRMED")
        if (evidence["surface"] != "/items/" or evidence["route_prefix"] != "/go/"
                or type(evidence["public_id"]) is not str
                or PUBLIC_ID.fullmatch(evidence["public_id"]) is None
                or evidence["public_id"] != anchors["public_id"]
                or type(evidence["cta_count"]) is not int or evidence["cta_count"] != 1
                or type(evidence["item_count"]) is not int or evidence["item_count"] != 100):
            return _decision(BLOCKED, False, "EXACT_ONE_CTA_SCOPE_INVALID")
        if (evidence["compliance_candidate_sha256"] != evidence["candidate_sha256"]
                or evidence["user_candidate_sha256"] != evidence["candidate_sha256"]):
            return _decision(BLOCKED, False, "APPROVAL_CANDIDATE_SHA_MISMATCH")
        if (type(evidence["rollback_worker_version"]) is not str
                or not evidence["rollback_worker_version"]
                or evidence["rollback_worker_version"] != anchors["rollback_worker_version"]):
            return _decision(BLOCKED, False, "ROLLBACK_TARGET_INVALID")
        observed = _timestamp(evidence["observed_at"])
        valid_until = _timestamp(evidence["valid_until"])
        free_confirmed = _timestamp(evidence["free_confirmed_at"])
        current = now.astimezone(timezone.utc)
        if (not observed <= current < valid_until
                or not timedelta(0) < valid_until - observed <= MAX_AGE):
            return _decision(BLOCKED, False, "ARTIFACT_STALE_OR_INVALID")
        if not timedelta(0) <= current - free_confirmed <= MAX_AGE:
            return _decision(BLOCKED, False, "FREE_PLAN_CONFIRMATION_STALE")
        return _decision(READY, True, "REVIEW_ONLY_ROUTE_SMOKE_AND_OUTCOME_UNVERIFIED")
    except (TypeError, ValueError, KeyError):
        return _decision(BLOCKED, False, "INPUT_INVALID")
    except Exception:
        return _decision(BLOCKED, False, "PREFLIGHT_ERROR")


def evaluate_one_row_delta(
    value: Any, evidence: Any, anchors: Any, *, now: Any
) -> Decision:
    """Assess sanitized hypothetical before/after counts; never execute SQL."""
    try:
        cta = evaluate_cta(evidence, anchors, now=now)
        if (type(value) is not dict or set(value) != DELTA_FIELDS
                or cta.status != READY or cta.review_ready is not True):
            return _decision(DELTA_BLOCKED, False, "CTA_REVIEW_AND_DELTA_REQUIRED")
        if (not _digest(value["candidate_sha256"])
                or type(value["public_id"]) is not str
                or PUBLIC_ID.fullmatch(value["public_id"]) is None
                or value["candidate_sha256"] != evidence["candidate_sha256"]
                or value["public_id"] != evidence["public_id"]):
            return _decision(DELTA_BLOCKED, False, "DELTA_IDENTITY_INVALID")
        counts = ("before_total", "before_enabled", "before_eligible",
                  "matched_row_count", "affected_row_count", "after_total",
                  "after_enabled", "after_eligible")
        if any(type(value[field]) is not int for field in counts):
            return _decision(DELTA_BLOCKED, False, "DELTA_COUNTS_INVALID")
        if (value["before_total"] != 867 or value["before_enabled"] != 0
                or value["before_eligible"] != 0 or value["matched_row_count"] != 1
                or value["affected_row_count"] != 1 or value["after_total"] != 867
                or value["after_enabled"] != 1 or value["after_eligible"] != 1
                or value["eligible_id_matches"] is not True):
            return _decision(DELTA_BLOCKED, False, "EXACT_ZERO_TO_ONE_DELTA_REQUIRED")
        return _decision(DELTA_READY, True, "REVIEW_ONLY_NO_D1_WRITE_AUTHORIZED")
    except (TypeError, ValueError, KeyError):
        return _decision(DELTA_BLOCKED, False, "DELTA_INPUT_INVALID")
    except Exception:
        return _decision(DELTA_BLOCKED, False, "DELTA_PREFLIGHT_ERROR")
