"""Read-only lifecycle eligibility for review while publication remains closed."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Any
import publication_gate
import revenue_mvp_official_lifecycle_policy as lifecycle

REVIEW_CANDIDATE = "OFFLINE_REVIEW_CANDIDATE"
BLOCKED = "OFFLINE_REVIEW_BLOCKED"

@dataclass(frozen=True)
class ReviewCandidate:
    status: str
    eligible: bool
    publication_allowed: bool = False
    affiliate_eligibility_allowed: bool = False
    gate_mutation_allowed: bool = False
    production_write_performed: bool = False
    cta_allowed: bool = False
    api_order_label_allowed: bool = False

def evaluate(decision: Any, gate: Any, *, freshness_confirmed: Any) -> ReviewCandidate:
    """Never includes an artifact or authorizes publication, regardless of Gate."""
    if (type(decision) is not lifecycle.OfficialLifecycleDecision
            or type(gate) is not publication_gate.PublicationGateResult
            or type(freshness_confirmed) is not bool
            or decision.version != lifecycle.POLICY_VERSION
            or decision.publication_gate_change_allowed is not False
            or decision.public_rank_number_allowed is not False
            or decision.offset_rank_allowed is not False
            or decision.update_frequency_claim_allowed is not False
            or decision.state is not lifecycle.EligibilityState.CANDIDATE
            or not freshness_confirmed
            or not isinstance(decision.observation_observed_at, datetime)
            or decision.observation_observed_at.tzinfo is None):
        return ReviewCandidate(BLOCKED, False)
    return ReviewCandidate(REVIEW_CANDIDATE, True)
