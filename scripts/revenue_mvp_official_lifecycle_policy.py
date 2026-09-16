"""Pure fail-closed policy for the confirmed 2026-09-16 lifecycle rules."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from product_verification import Observation, VerificationObservation


POLICY_VERSION = "2026-09-16.1"
MAX_ERROR_RETRY_ATTEMPTS = 1
MAX_ERROR_WAIT_SECONDS = 300
OFFSET_SEMANTICS = "PAGINATION_SEARCH_START_POSITION"
FIRST_POSITION_SEMANTICS = "PAGINATION_SEARCH_START_POSITION"


class InventorySignal(str, Enum):
    PREORDER = "PREORDER"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class EligibilityState(str, Enum):
    CANDIDATE = "ELIGIBILITY_CANDIDATE"
    EXCLUDED = "EXCLUDED"
    TEMPORARILY_BLOCKED = "TEMPORARILY_BLOCKED"
    FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class OfficialLifecycleDecision:
    version: str
    state: EligibilityState
    public_listing_candidate: bool
    affiliate_candidate: bool
    exclude_from_public_site: bool
    requery_permitted: bool
    bounded_wait_required: bool
    stop_on_rate_limit: bool
    retry_attempt_limit: int
    wait_seconds_upper_bound: int
    inventory_signal_only: bool
    internal_history_retention_allowed: bool
    public_rank_number_allowed: bool
    offset_rank_allowed: bool
    update_frequency_claim_allowed: bool
    publication_gate_change_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["state"] = self.state.value
        value["reason_codes"] = list(self.reason_codes)
        return value


def _decision(
    state: EligibilityState,
    *,
    candidate: bool = False,
    requery: bool = False,
    wait: bool = False,
    inventory_signal_only: bool = False,
    reasons: tuple[str, ...],
) -> OfficialLifecycleDecision:
    return OfficialLifecycleDecision(
        POLICY_VERSION,
        state,
        candidate,
        candidate,
        not candidate,
        requery,
        wait,
        True,
        MAX_ERROR_RETRY_ATTEMPTS if wait else 0,
        MAX_ERROR_WAIT_SECONDS if wait else 0,
        inventory_signal_only,
        False,
        False,
        False,
        False,
        False,
        reasons,
    )


def evaluate_official_lifecycle_policy(
    observation: Any,
    *,
    inventory_signal: Any = InventorySignal.UNKNOWN,
) -> OfficialLifecycleDecision:
    """Evaluate sanitized facts without accepting URLs or changing any Gate."""

    try:
        if type(observation) is not VerificationObservation:
            return _decision(
                EligibilityState.FAIL_CLOSED,
                reasons=("OBSERVATION_CONTRACT_INVALID",),
            )
        try:
            observation_type = Observation(observation.observation)
            inventory = InventorySignal(inventory_signal)
        except (TypeError, ValueError):
            return _decision(
                EligibilityState.FAIL_CLOSED,
                reasons=("SANITIZED_FACT_INVALID",),
            )
        if type(observation.affiliate_link_observed) not in {bool, type(None)}:
            return _decision(
                EligibilityState.FAIL_CLOSED,
                reasons=("AFFILIATE_LINK_PRESENCE_INVALID",),
            )
        if (
            not isinstance(observation.observed_at, datetime)
            or observation.observed_at.tzinfo is None
            or type(observation.reason_codes) is not tuple
            or not observation.reason_codes
            or any(type(code) is not str or not code for code in observation.reason_codes)
        ):
            return _decision(
                EligibilityState.FAIL_CLOSED,
                reasons=("OBSERVATION_ENVELOPE_INVALID",),
            )

        expected_shape = {
            Observation.API_ITEM_VISIBLE: (True, {True, False, None}),
            Observation.API_ITEM_NOT_RETURNED: (False, {None}),
            Observation.API_RATE_LIMITED: (None, {None}),
            Observation.API_ERROR: (None, {None}),
        }.get(observation_type)
        if expected_shape is not None and (
            observation.expected_content_id_match is not expected_shape[0]
            or observation.affiliate_link_observed not in expected_shape[1]
        ):
            return _decision(
                EligibilityState.FAIL_CLOSED,
                reasons=("OBSERVATION_SHAPE_CONTRADICTORY",),
            )

        if observation_type == Observation.API_ITEM_NOT_RETURNED:
            return _decision(
                EligibilityState.EXCLUDED,
                requery=True,
                reasons=(
                    "API_UNAVAILABLE_EXCLUDED_FROM_AFFILIATE",
                    "API_UNAVAILABLE_EXCLUDED_FROM_PUBLIC_SITE",
                    "REQUERY_FREQUENCY_NOT_DEFINED",
                ),
            )
        if observation_type in {Observation.API_RATE_LIMITED, Observation.API_ERROR}:
            return _decision(
                EligibilityState.TEMPORARILY_BLOCKED,
                requery=True,
                wait=True,
                reasons=(
                    "API_ERROR_REQUIRES_BOUNDED_WAIT",
                    "RATE_LIMIT_MUST_BE_RESPECTED",
                    "REQUERY_FREQUENCY_NOT_DEFINED",
                ),
            )
        if observation_type != Observation.API_ITEM_VISIBLE:
            return _decision(
                EligibilityState.FAIL_CLOSED,
                reasons=("OBSERVATION_NOT_ELIGIBLE",),
            )
        if observation.affiliate_link_observed is not True:
            return _decision(
                EligibilityState.EXCLUDED,
                requery=True,
                reasons=(
                    "AFFILIATE_URL_ABSENT_OR_UNKNOWN",
                    "EXCLUDED_FROM_AFFILIATE_AND_PUBLIC_SITE",
                    "REQUERY_FREQUENCY_NOT_DEFINED",
                ),
            )

        inventory_only = inventory in {
            InventorySignal.PREORDER,
            InventorySignal.OUT_OF_STOCK,
        }
        return _decision(
            EligibilityState.CANDIDATE,
            candidate=True,
            inventory_signal_only=inventory_only,
            reasons=(
                "API_VISIBLE_WITH_AFFILIATE_URL",
                "INVENTORY_SIGNAL_DOES_NOT_EXCLUDE" if inventory_only
                else "NO_INVENTORY_ONLY_EXCLUSION",
                "PUBLICATION_GATE_REMAINS_SEPARATE",
            ),
        )
    except Exception:
        return _decision(
            EligibilityState.FAIL_CLOSED,
            reasons=("OFFICIAL_LIFECYCLE_POLICY_ERROR",),
        )


__all__ = [
    "EligibilityState",
    "InventorySignal",
    "MAX_ERROR_RETRY_ATTEMPTS",
    "MAX_ERROR_WAIT_SECONDS",
    "OFFSET_SEMANTICS",
    "FIRST_POSITION_SEMANTICS",
    "OfficialLifecycleDecision",
    "POLICY_VERSION",
    "evaluate_official_lifecycle_policy",
]
