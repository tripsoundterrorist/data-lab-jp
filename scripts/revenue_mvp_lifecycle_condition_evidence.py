"""Read-only evidence for fail-closed lifecycle condition handling."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
from typing import Any

import lifecycle_decision
import product_lifecycle
from product_verification import Observation, VerificationObservation


VERSION = "0.1"
EVIDENCE_READY = "IMPLEMENTATION_EVIDENCE_READY"
BLOCKED = "BLOCKED"
AS_OF = datetime(2026, 9, 8, tzinfo=timezone.utc)
POLICY = product_lifecycle.LifecyclePolicy(
    observation_recency_window=timedelta(days=2),
    verification_ttl=timedelta(days=3),
)


@dataclass(frozen=True)
class LifecycleConditionEvidence:
    version: str
    status: str
    implementation_evidence_candidate: bool
    official_semantics_resolved: bool
    publication_gate_unlock_allowed: bool
    checks_passed: int
    checks_required: int
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _observation(value: Observation) -> VerificationObservation:
    return VerificationObservation(
        observation=value,
        observed_at=AS_OF,
        expected_content_id_match=None,
        affiliate_link_observed=None,
        source_status_code=200,
        reason_codes=("EVIDENCE_FIXTURE",),
    )


def _verification(value: str) -> dict[str, Any]:
    return {
        "verification_source": "AVAILABILITY_VERIFIER",
        "verified_at": (AS_OF - timedelta(hours=1)).isoformat(),
        "verification_result": value,
        "verification_reason": "EXPLICIT_CHECK",
        "source_status_code": None,
    }


def assess_lifecycle_condition_evidence() -> LifecycleConditionEvidence:
    """Exercise exact safety properties without changing lifecycle state."""

    try:
        stale = product_lifecycle.evaluate_product_lifecycle(
            last_observed_at=(AS_OF - timedelta(days=365)).isoformat(),
            verification=None,
            as_of=AS_OF,
            policy=POLICY,
        )
        unavailable = product_lifecycle.evaluate_product_lifecycle(
            last_observed_at=None,
            verification=_verification("unavailable"),
            as_of=AS_OF,
            policy=POLICY,
        )
        not_returned = lifecycle_decision.evaluate_lifecycle_decision(
            _observation(Observation.API_ITEM_NOT_RETURNED)
        )
        visible = lifecycle_decision.evaluate_lifecycle_decision(
            _observation(Observation.API_ITEM_VISIBLE)
        )
        confirmation_only = lifecycle_decision.evaluate_lifecycle_decision(
            _observation(Observation.API_ITEM_VISIBLE),
            official_policy_confirmed=True,
        )
        checks = (
            stale.state == product_lifecycle.LifecycleState.VERIFICATION_DUE
            and stale.lifecycle_eligible_for_publication is False,
            unavailable.state
            == product_lifecycle.LifecycleState.CONFIRMED_UNAVAILABLE
            and unavailable.lifecycle_eligible_for_publication is False,
            not_returned.decision_state
            == lifecycle_decision.DecisionState.REVERIFY_REQUIRED
            and not_returned.requires_reverification is True
            and not_returned.publication_lifecycle_eligible is False,
            visible.decision_state
            == lifecycle_decision.DecisionState.OBSERVATION_ACCEPTED
            and visible.publication_lifecycle_eligible is False,
            confirmation_only.decision_state
            == lifecycle_decision.DecisionState.POLICY_BLOCKED
            and confirmation_only.publication_lifecycle_eligible is False,
        )
        passed = sum(check is True for check in checks)
        ready = passed == len(checks)
        return LifecycleConditionEvidence(
            VERSION,
            EVIDENCE_READY if ready else BLOCKED,
            ready,
            False,
            False,
            passed,
            len(checks),
            (
                "FAIL_CLOSED_LIFECYCLE_CONDITIONS_VERIFIED",
                "SEPARATE_OFFICIAL_SEMANTICS_REQUIRED",
            ) if ready else ("LIFECYCLE_CONDITION_EVIDENCE_INCOMPLETE",),
        )
    except Exception:
        return LifecycleConditionEvidence(
            VERSION, BLOCKED, False, False, False, 0, 5,
            ("LIFECYCLE_CONDITION_EVIDENCE_INTERNAL_ERROR",),
        )


def main() -> int:
    result = assess_lifecycle_condition_evidence()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {EVIDENCE_READY, BLOCKED} else 2


if __name__ == "__main__":
    raise SystemExit(main())
