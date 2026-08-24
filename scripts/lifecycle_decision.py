"""Fail-closed translation from API observations to lifecycle-safe decisions.

Policy version 0.1 deliberately assigns no availability, affiliate, or
publication meaning.  It only says how an observation should be handled next.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from product_verification import Observation, VerificationObservation


POLICY_VERSION = "0.1"


class DecisionState(str, Enum):
    DECISION_PENDING = "DECISION_PENDING"
    REVERIFY_REQUIRED = "REVERIFY_REQUIRED"
    OBSERVATION_ACCEPTED = "OBSERVATION_ACCEPTED"
    OBSERVATION_ANOMALY = "OBSERVATION_ANOMALY"
    TEMPORARY_FAILURE = "TEMPORARY_FAILURE"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ReverificationPolicy:
    """Reserved, configurable thresholds; v0.1 never treats them as proof."""

    minimum_consecutive_not_returned: int = 3
    grace_period: timedelta = timedelta(days=7)


@dataclass(frozen=True)
class ReverificationContext:
    first_not_returned_at: datetime | None = None
    consecutive_not_returned_count: int = 0
    last_successful_visibility_at: datetime | None = None
    next_verification_due_at: datetime | None = None


@dataclass(frozen=True)
class LifecycleDecision:
    decision_state: DecisionState
    publication_lifecycle_eligible: bool
    requires_reverification: bool
    reason_codes: tuple[str, ...]
    policy_version: str
    official_policy_confirmed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_state": self.decision_state.value,
            "publication_lifecycle_eligible": self.publication_lifecycle_eligible,
            "requires_reverification": self.requires_reverification,
            "reason_codes": list(self.reason_codes),
            "policy_version": self.policy_version,
            "official_policy_confirmed": self.official_policy_confirmed,
        }


_MAPPING = {
    Observation.API_ITEM_VISIBLE: (
        DecisionState.OBSERVATION_ACCEPTED,
        False,
        "VISIBILITY_OBSERVED_NO_LIFECYCLE_MEANING",
    ),
    Observation.API_ITEM_NOT_RETURNED: (
        DecisionState.REVERIFY_REQUIRED,
        True,
        "NON_RETURN_REQUIRES_REVERIFICATION",
    ),
    Observation.API_RATE_LIMITED: (
        DecisionState.TEMPORARY_FAILURE,
        True,
        "RATE_LIMIT_RETRY_LATER",
    ),
    Observation.API_ERROR: (
        DecisionState.TEMPORARY_FAILURE,
        True,
        "API_ERROR_RETRY_LATER",
    ),
    Observation.CID_MISMATCH: (
        DecisionState.OBSERVATION_ANOMALY,
        True,
        "CID_MISMATCH_REQUIRES_REVIEW",
    ),
    Observation.MULTIPLE_ITEMS_RETURNED: (
        DecisionState.OBSERVATION_ANOMALY,
        True,
        "MULTIPLE_ITEMS_REQUIRE_REVIEW",
    ),
    Observation.MALFORMED_RESPONSE: (
        DecisionState.OBSERVATION_ANOMALY,
        True,
        "MALFORMED_RESPONSE_REQUIRES_REVIEW",
    ),
    Observation.UNKNOWN: (
        DecisionState.UNKNOWN,
        True,
        "UNKNOWN_OBSERVATION",
    ),
}


def _result(
    state: DecisionState,
    requires_reverification: bool,
    reason: str,
    *,
    official_policy_confirmed: bool,
) -> LifecycleDecision:
    return LifecycleDecision(
        decision_state=state,
        publication_lifecycle_eligible=False,
        requires_reverification=requires_reverification,
        reason_codes=(reason,),
        policy_version=POLICY_VERSION,
        official_policy_confirmed=official_policy_confirmed,
    )


def _valid_timestamp(value: datetime | None) -> bool:
    return value is None or (
        isinstance(value, datetime) and value.tzinfo is not None
    )


def _valid_policy_and_context(
    policy: ReverificationPolicy, context: ReverificationContext
) -> bool:
    return (
        isinstance(policy, ReverificationPolicy)
        and isinstance(policy.minimum_consecutive_not_returned, int)
        and not isinstance(policy.minimum_consecutive_not_returned, bool)
        and policy.minimum_consecutive_not_returned > 0
        and isinstance(policy.grace_period, timedelta)
        and policy.grace_period > timedelta(0)
        and isinstance(context, ReverificationContext)
        and isinstance(context.consecutive_not_returned_count, int)
        and not isinstance(context.consecutive_not_returned_count, bool)
        and context.consecutive_not_returned_count >= 0
        and _valid_timestamp(context.first_not_returned_at)
        and _valid_timestamp(context.last_successful_visibility_at)
        and _valid_timestamp(context.next_verification_due_at)
    )


def evaluate_lifecycle_decision(
    observation: VerificationObservation,
    *,
    reverification_policy: ReverificationPolicy = ReverificationPolicy(),
    reverification_context: ReverificationContext = ReverificationContext(),
    official_policy_confirmed: bool = False,
) -> LifecycleDecision:
    """Translate observation handling only; all business decisions stay closed."""

    try:
        if not isinstance(official_policy_confirmed, bool):
            return _result(
                DecisionState.UNKNOWN,
                True,
                "INVALID_OFFICIAL_POLICY_GATE",
                official_policy_confirmed=False,
            )
        if not _valid_policy_and_context(
            reverification_policy, reverification_context
        ):
            return _result(
                DecisionState.UNKNOWN,
                True,
                "INVALID_REVERIFICATION_POLICY",
                official_policy_confirmed=official_policy_confirmed,
            )
        if not isinstance(observation, VerificationObservation):
            return _result(
                DecisionState.UNKNOWN,
                True,
                "INVALID_OBSERVATION_CONTRACT",
                official_policy_confirmed=official_policy_confirmed,
            )
        try:
            observation_type = Observation(observation.observation)
            state, reverify, reason = _MAPPING[observation_type]
        except (KeyError, TypeError, ValueError):
            return _result(
                DecisionState.UNKNOWN,
                True,
                "UNKNOWN_OBSERVATION_TYPE",
                official_policy_confirmed=official_policy_confirmed,
            )

        # Confirmation alone cannot activate semantics absent from this version.
        if official_policy_confirmed:
            return _result(
                DecisionState.POLICY_BLOCKED,
                True,
                "CONFIRMED_POLICY_NOT_IMPLEMENTED_IN_VERSION",
                official_policy_confirmed=True,
            )
        return _result(
            state,
            reverify,
            reason,
            official_policy_confirmed=False,
        )
    except Exception:
        return _result(
            DecisionState.UNKNOWN,
            True,
            "INTERNAL_DECISION_ERROR",
            official_policy_confirmed=False,
        )


__all__ = [
    "DecisionState",
    "LifecycleDecision",
    "POLICY_VERSION",
    "ReverificationContext",
    "ReverificationPolicy",
    "evaluate_lifecycle_decision",
]
