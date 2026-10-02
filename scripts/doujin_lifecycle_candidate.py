"""Collection-only doujin adapter for the confirmed lifecycle policy.

This module deliberately does not accept raw API payloads, URLs, identifiers,
or credentials.  A technically viable lifecycle result remains non-public
until the exact doujin source scope is confirmed separately.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from product_verification import Observation, VerificationObservation
from revenue_mvp_official_lifecycle_policy import (
    EligibilityState,
    InventorySignal,
    evaluate_official_lifecycle_policy,
)


ADAPTER_VERSION = "2026-10-02.1"
ALLOWED_CONTENT_TYPES = frozenset({"doujin", "doujin_bl", "doujin_tl"})


@dataclass(frozen=True)
class DoujinLifecycleObservation:
    version: str
    content_type: str
    observation: Observation
    observed_at: datetime | None
    expected_content_id_match: bool | None
    affiliate_link_observed: bool | None
    inventory_signal: InventorySignal
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class DoujinLifecycleCandidateDecision:
    version: str
    status: str
    underlying_lifecycle_state: str
    underlying_lifecycle_candidate: bool
    exact_doujin_source_scope_confirmed: bool
    public_listing_candidate: bool
    affiliate_candidate: bool
    exclude_from_public_site: bool
    requery_permitted: bool
    bounded_wait_required: bool
    retry_attempt_limit: int
    wait_seconds_upper_bound: int
    internal_history_retention_allowed: bool
    publication_gate_change_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["reason_codes"] = list(self.reason_codes)
        return result


def _fail_closed(reason: str) -> DoujinLifecycleCandidateDecision:
    return DoujinLifecycleCandidateDecision(
        ADAPTER_VERSION,
        "FAIL_CLOSED",
        EligibilityState.FAIL_CLOSED.value,
        False,
        False,
        False,
        False,
        True,
        False,
        False,
        0,
        0,
        False,
        False,
        (reason,),
    )


def evaluate_doujin_lifecycle_candidate(
    value: Any,
) -> DoujinLifecycleCandidateDecision:
    """Evaluate sanitized doujin facts without granting publication rights."""

    try:
        if type(value) is not DoujinLifecycleObservation:
            return _fail_closed("DOUJIN_OBSERVATION_CONTRACT_INVALID")
        if value.version != ADAPTER_VERSION:
            return _fail_closed("DOUJIN_OBSERVATION_VERSION_UNSUPPORTED")
        if value.content_type not in ALLOWED_CONTENT_TYPES:
            return _fail_closed("DOUJIN_CONTENT_TYPE_NOT_ALLOWED")

        observation = VerificationObservation(
            observation=value.observation,
            observed_at=value.observed_at,
            expected_content_id_match=value.expected_content_id_match,
            affiliate_link_observed=value.affiliate_link_observed,
            source_status_code=None,
            reason_codes=value.reason_codes,
        )
        lifecycle = evaluate_official_lifecycle_policy(
            observation,
            inventory_signal=value.inventory_signal,
        )

        if lifecycle.state is EligibilityState.CANDIDATE:
            status = "READY_FOR_EXACT_DOUJIN_SCOPE_REVIEW"
            reasons = lifecycle.reason_codes + (
                "EXACT_DOUJIN_SOURCE_SCOPE_NOT_CONFIRMED",
                "PUBLICATION_AND_AFFILIATE_REMAIN_DISABLED",
            )
        else:
            status = lifecycle.state.value
            reasons = lifecycle.reason_codes

        return DoujinLifecycleCandidateDecision(
            ADAPTER_VERSION,
            status,
            lifecycle.state.value,
            lifecycle.state is EligibilityState.CANDIDATE,
            False,
            False,
            False,
            True,
            lifecycle.requery_permitted,
            lifecycle.bounded_wait_required,
            lifecycle.retry_attempt_limit,
            lifecycle.wait_seconds_upper_bound,
            False,
            False,
            reasons,
        )
    except Exception:
        return _fail_closed("DOUJIN_LIFECYCLE_ADAPTER_ERROR")


__all__ = [
    "ADAPTER_VERSION",
    "ALLOWED_CONTENT_TYPES",
    "DoujinLifecycleCandidateDecision",
    "DoujinLifecycleObservation",
    "evaluate_doujin_lifecycle_candidate",
]
