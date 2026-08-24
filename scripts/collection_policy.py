"""Pure, fail-closed collection policy for separated API populations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


POLICY_VERSION = "0.1"
POPULATION_IDENTITY_FIELDS = (
    "site",
    "service",
    "floor",
    "source_sort",
    "offset",
    "hits",
)


class PolicyStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPERIMENTAL = "EXPERIMENTAL"
    BLOCKED = "BLOCKED"
    PENDING_VALIDATION = "PENDING_VALIDATION"
    DISABLED = "DISABLED"


class Cadence(str, Enum):
    DAILY = "DAILY"
    LESS_THAN_DAILY = "LESS_THAN_DAILY"
    MANUAL = "MANUAL"


@dataclass(frozen=True)
class ProductionEligibilityGates:
    official_sort_definition_confirmed: bool = False
    reproducibility_validated: bool = False
    temporal_stability_validated: bool = False
    request_budget_validated: bool = False
    rate_limit_safety_validated: bool = False
    database_schema_ready: bool = False
    collector_integration_tested: bool = False

    def all_confirmed(self) -> bool:
        return all(
            value is True
            for value in (
                self.official_sort_definition_confirmed,
                self.reproducibility_validated,
                self.temporal_stability_validated,
                self.request_budget_validated,
                self.rate_limit_safety_validated,
                self.database_schema_ready,
                self.collector_integration_tested,
            )
        )


@dataclass(frozen=True)
class CollectionPolicy:
    policy_version: str
    source_sort: str
    enabled: bool
    status: PolicyStatus
    hits: int
    offsets: tuple[int, ...]
    max_requests_per_run: int
    minimum_delay_between_requests_seconds: float
    stop_on_rate_limit: bool
    retry_count: int
    automatic_pagination: bool
    cadence: Cadence
    priority: int
    observation_role: tuple[str, ...]
    position_semantics: str
    review_sort_semantics: str | None
    publication_use_allowed: bool
    experimental: bool
    configured_values_are_candidates: bool
    selection_bias_warning: str | None
    review_numeric_observation_allowed: bool
    review_body_requested: bool
    temporal_probe_required: bool
    minimum_temporal_probe_count: int
    temporal_probe_count_is_experimental_assumption: bool
    eligibility_gates: ProductionEligibilityGates | None


@dataclass(frozen=True)
class PolicyEvaluation:
    valid: bool
    production_collection_eligible: bool
    reason_codes: tuple[str, ...]
    request_count: int
    candidate_total_items: int
    population_identity_fields: tuple[str, ...] = POPULATION_IDENTITY_FIELDS


def date_policy() -> CollectionPolicy:
    """Describe the existing date collector without changing its behavior."""

    return CollectionPolicy(
        policy_version=POLICY_VERSION,
        source_sort="date",
        enabled=True,
        status=PolicyStatus.ACTIVE,
        hits=50,
        offsets=(1, 51),
        max_requests_per_run=2,
        minimum_delay_between_requests_seconds=1.0,
        stop_on_rate_limit=True,
        retry_count=0,
        automatic_pagination=False,
        cadence=Cadence.DAILY,
        priority=100,
        observation_role=("discovery", "freshness", "price observation"),
        position_semantics="date-sorted observation position",
        review_sort_semantics=None,
        publication_use_allowed=False,
        experimental=False,
        configured_values_are_candidates=False,
        selection_bias_warning=None,
        review_numeric_observation_allowed=True,
        review_body_requested=False,
        temporal_probe_required=False,
        minimum_temporal_probe_count=0,
        temporal_probe_count_is_experimental_assumption=False,
        eligibility_gates=None,
    )


def rank_candidate_policy() -> CollectionPolicy:
    return CollectionPolicy(
        policy_version=POLICY_VERSION,
        source_sort="rank",
        enabled=False,
        status=PolicyStatus.PENDING_VALIDATION,
        hits=100,
        offsets=(1, 101),
        max_requests_per_run=2,
        minimum_delay_between_requests_seconds=1.0,
        stop_on_rate_limit=True,
        retry_count=0,
        automatic_pagination=False,
        cadence=Cadence.DAILY,
        priority=50,
        observation_role=(
            "rank-sorted observation",
            "review numeric observation",
        ),
        position_semantics="rank-sorted observation position",
        review_sort_semantics=None,
        publication_use_allowed=False,
        experimental=True,
        configured_values_are_candidates=True,
        selection_bias_warning="separate from date and review populations",
        review_numeric_observation_allowed=True,
        review_body_requested=False,
        temporal_probe_required=True,
        minimum_temporal_probe_count=2,
        temporal_probe_count_is_experimental_assumption=True,
        eligibility_gates=ProductionEligibilityGates(),
    )


def review_candidate_policy(*, include_second_page: bool = False) -> CollectionPolicy:
    offsets = (1, 101) if include_second_page else (1,)
    return CollectionPolicy(
        policy_version=POLICY_VERSION,
        source_sort="review",
        enabled=False,
        status=PolicyStatus.PENDING_VALIDATION,
        hits=100,
        offsets=offsets,
        max_requests_per_run=len(offsets),
        minimum_delay_between_requests_seconds=1.0,
        stop_on_rate_limit=True,
        retry_count=0,
        automatic_pagination=False,
        cadence=Cadence.LESS_THAN_DAILY,
        priority=25,
        observation_role=("review-sorted population observation",),
        position_semantics="review-sorted observation position",
        review_sort_semantics="review-sorted population",
        publication_use_allowed=False,
        experimental=True,
        configured_values_are_candidates=True,
        selection_bias_warning="not the same sampling population as date or rank",
        review_numeric_observation_allowed=True,
        review_body_requested=False,
        temporal_probe_required=True,
        minimum_temporal_probe_count=2,
        temporal_probe_count_is_experimental_assumption=True,
        eligibility_gates=ProductionEligibilityGates(),
    )


def _valid_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _invalid_reasons(policy: CollectionPolicy) -> set[str]:
    reasons: set[str] = set()
    if policy.policy_version != POLICY_VERSION:
        reasons.add("UNSUPPORTED_POLICY_VERSION")
    if policy.source_sort not in {"date", "rank", "review"}:
        reasons.add("UNKNOWN_SORT")
    if not isinstance(policy.status, PolicyStatus):
        reasons.add("UNKNOWN_STATUS")
    if not isinstance(policy.cadence, Cadence):
        reasons.add("UNKNOWN_CADENCE")
    if not _valid_bool(policy.enabled) or not _valid_bool(policy.experimental):
        reasons.add("MALFORMED_POLICY")
    if isinstance(policy.hits, bool) or not isinstance(policy.hits, int) or policy.hits <= 0:
        reasons.add("INVALID_HITS")
    if not isinstance(policy.offsets, tuple) or not policy.offsets:
        reasons.add("INVALID_OFFSETS")
    elif any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in policy.offsets):
        reasons.add("INVALID_OFFSETS")
    elif len(set(policy.offsets)) != len(policy.offsets):
        reasons.add("DUPLICATE_OFFSETS")
    elif any(
        right < left + policy.hits
        for left, right in zip(sorted(policy.offsets), sorted(policy.offsets)[1:])
    ):
        reasons.add("PAGE_OVERLAP")
    if (
        isinstance(policy.max_requests_per_run, bool)
        or not isinstance(policy.max_requests_per_run, int)
        or policy.max_requests_per_run != len(policy.offsets)
        or policy.max_requests_per_run < 1
        or policy.max_requests_per_run > 2
    ):
        reasons.add("REQUEST_BUDGET_MISMATCH")
    if (
        isinstance(policy.minimum_delay_between_requests_seconds, bool)
        or not isinstance(policy.minimum_delay_between_requests_seconds, (int, float))
        or policy.minimum_delay_between_requests_seconds < 0
    ):
        reasons.add("INVALID_REQUEST_DELAY")
    if isinstance(policy.retry_count, bool) or not isinstance(policy.retry_count, int) or policy.retry_count < 0:
        reasons.add("INVALID_RETRY_COUNT")
    if not _valid_bool(policy.automatic_pagination) or policy.automatic_pagination:
        reasons.add("AUTOMATIC_PAGINATION_FORBIDDEN")
    if policy.review_body_requested is not False:
        reasons.add("REVIEW_BODY_FORBIDDEN")
    if policy.source_sort == "rank" and policy.position_semantics != "rank-sorted observation position":
        reasons.add("INVALID_RANK_SEMANTICS")
    if policy.source_sort == "review" and policy.review_sort_semantics != "review-sorted population":
        reasons.add("UNCONFIRMED_REVIEW_SEMANTICS")
    if policy.source_sort in {"rank", "review"}:
        if not policy.experimental or not policy.configured_values_are_candidates:
            reasons.add("EXPERIMENTAL_MARKER_REQUIRED")
        if policy.enabled:
            reasons.add("EXPERIMENTAL_POLICY_ENABLED")
        if policy.stop_on_rate_limit is not True:
            reasons.add("RATE_LIMIT_STOP_REQUIRED")
        if policy.retry_count != 0:
            reasons.add("EXPERIMENTAL_RETRY_FORBIDDEN")
        if not policy.temporal_probe_required:
            reasons.add("TEMPORAL_VALIDATION_REQUIRED")
        if (
            policy.minimum_temporal_probe_count <= 0
            or not policy.temporal_probe_count_is_experimental_assumption
        ):
            reasons.add("INVALID_TEMPORAL_ASSUMPTION")
        if not isinstance(policy.eligibility_gates, ProductionEligibilityGates):
            reasons.add("ELIGIBILITY_GATES_MISSING")
    elif policy.eligibility_gates is not None:
        reasons.add("UNEXPECTED_ELIGIBILITY_GATES")
    return reasons


def evaluate_collection_policy(policy: Any) -> PolicyEvaluation:
    try:
        if not isinstance(policy, CollectionPolicy):
            return PolicyEvaluation(False, False, ("MALFORMED_POLICY",), 0, 0)
        reasons = _invalid_reasons(policy)
        valid = not reasons
        production_eligible = (
            valid
            and policy.source_sort == "date"
            and policy.enabled
            and policy.status is PolicyStatus.ACTIVE
            and not policy.experimental
        )
        # In v0.1, experimental sorts remain blocked even if all gate values
        # are mechanically true; a later version must explicitly add promotion.
        return PolicyEvaluation(
            valid=valid,
            production_collection_eligible=production_eligible,
            reason_codes=tuple(sorted(reasons)),
            request_count=len(policy.offsets) if isinstance(policy.offsets, tuple) else 0,
            candidate_total_items=(
                policy.hits * len(policy.offsets)
                if isinstance(policy.hits, int)
                and not isinstance(policy.hits, bool)
                and isinstance(policy.offsets, tuple)
                else 0
            ),
        )
    except Exception:
        return PolicyEvaluation(False, False, ("INTERNAL_POLICY_ERROR",), 0, 0)


__all__ = [
    "Cadence",
    "CollectionPolicy",
    "POLICY_VERSION",
    "POPULATION_IDENTITY_FIELDS",
    "PolicyEvaluation",
    "PolicyStatus",
    "ProductionEligibilityGates",
    "date_policy",
    "evaluate_collection_policy",
    "rank_candidate_policy",
    "review_candidate_policy",
]
