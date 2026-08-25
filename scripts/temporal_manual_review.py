"""Pure manual-review policy for review-eligible temporal observations.

The policy consumes aggregate comparison values only.  It neither reads state
files nor changes collection, blocker, gate, database, or publication state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Any, Mapping, Sequence

from collection_policy import (
    evaluate_collection_policy,
    rank_candidate_policy,
    review_candidate_policy,
)
from official_blocker_policy import PENDING_OFFICIAL_CONFIRMATION, SORT_BLOCKER, blocker_for
from temporal_runbook_policy import FIXED_POPULATIONS
from temporal_stability_policy import (
    HIGH,
    LOW,
    MODERATE,
    OBSERVATION_ONLY,
    REVIEW_ELIGIBLE,
    StabilityInput,
    assess_temporal_stability,
)


REVIEW_POLICY_VERSION = "0.1"
CONSISTENCY_THRESHOLD = 0.20
ACCEPTABLE = "ACCEPTABLE"
VARIABLE = "VARIABLE"
UNKNOWN = "UNKNOWN"

NOT_REVIEW_ELIGIBLE = "NOT_REVIEW_ELIGIBLE"
CONTINUE_OBSERVATION = "CONTINUE_OBSERVATION"
INTERNAL_CANDIDATE = "INTERNAL_CANDIDATE"
HOLD_FOR_ANOMALY = "HOLD_FOR_ANOMALY"
HOLD_FOR_OFFICIAL_SEMANTICS = "HOLD_FOR_OFFICIAL_SEMANTICS"
INSUFFICIENT_CONSISTENCY = "INSUFFICIENT_CONSISTENCY"
MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
OUTCOMES = frozenset({
    NOT_REVIEW_ELIGIBLE, CONTINUE_OBSERVATION, INTERNAL_CANDIDATE,
    HOLD_FOR_ANOMALY, HOLD_FOR_OFFICIAL_SEMANTICS,
    INSUFFICIENT_CONSISTENCY, MANUAL_REVIEW_REQUIRED,
})
SEMANTICS_PENDING = "PENDING"
SEMANTICS_CONFIRMED = "CONFIRMED"
ALLOWED_BANDS = frozenset({LOW, MODERATE, HIGH})
COMPARISON_FIELDS = frozenset({
    "captured_at", "interval_hours", "previous_count", "current_count",
    "retained_count", "entered_count", "exited_count", "retention_rate",
    "jaccard", "turnover_rate", "observation_band", "classification",
    "production_readiness",
})
FORBIDDEN_KEY = re.compile(
    r"(?i)(?:content|product|api|affiliate)[_-]?ids?$|anonymous|title|url|"
    r"path|credential|password|secret|token|raw|exception|traceback"
)


@dataclass(frozen=True)
class ManualReviewResult:
    review_policy_version: str
    source_sort: str | None
    offset: int | None
    hits: int | None
    history_count: int | None
    review_eligible: bool
    composition_consistency: str
    retention_min: float | None
    retention_max: float | None
    retention_range: float | None
    outcome: str
    promotion_candidate: bool
    official_semantics_status: str
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **{key: value for key, value in self.__dict__.items() if key != "reason_codes"},
            "reason_codes": list(self.reason_codes),
        }


def _result(
    population: Any,
    history_count: Any,
    *,
    eligible: bool = False,
    consistency: str = UNKNOWN,
    retention_min: float | None = None,
    retention_max: float | None = None,
    retention_range: float | None = None,
    outcome: str,
    promotion: bool = False,
    semantics: str = SEMANTICS_PENDING,
    reasons: tuple[str, ...],
) -> ManualReviewResult:
    identity = population if isinstance(population, tuple) and len(population) == 3 else (None, None, None)
    return ManualReviewResult(
        REVIEW_POLICY_VERSION, identity[0], identity[1], identity[2],
        history_count if isinstance(history_count, int) and not isinstance(history_count, bool) else None,
        eligible, consistency, retention_min, retention_max, retention_range,
        outcome, promotion, semantics, tuple(sorted(set(reasons))),
    )


def _contains_forbidden(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            not isinstance(key, str)
            or FORBIDDEN_KEY.search(key) is not None
            or _contains_forbidden(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden(item) for item in value)
    return False


def _collection_still_blocked(source_sort: str) -> bool:
    policy = rank_candidate_policy() if source_sort == "rank" else review_candidate_policy(include_second_page=True)
    return evaluate_collection_policy(policy).production_collection_eligible is False


def _review(
    *,
    review_policy_version: Any,
    population: Any,
    history_count: Any,
    comparisons: Any,
    official_semantics_status: Any,
) -> ManualReviewResult:
    if review_policy_version != REVIEW_POLICY_VERSION:
        return _result(population, history_count, outcome=MANUAL_REVIEW_REQUIRED, reasons=("UNSUPPORTED_REVIEW_POLICY_VERSION",))
    if population not in FIXED_POPULATIONS:
        return _result(population, history_count, outcome=MANUAL_REVIEW_REQUIRED, reasons=("UNKNOWN_POPULATION",))
    if (
        not isinstance(history_count, int)
        or isinstance(history_count, bool)
        or history_count < 3
    ):
        return _result(population, history_count, outcome=NOT_REVIEW_ELIGIBLE, reasons=("HISTORY_NOT_REVIEW_ELIGIBLE",))
    if not isinstance(comparisons, Sequence) or isinstance(comparisons, (str, bytes)) or len(comparisons) < 3:
        return _result(population, history_count, outcome=NOT_REVIEW_ELIGIBLE, reasons=("MISSING_COMPARISON",))
    if len(comparisons) > history_count:
        return _result(population, history_count, outcome=MANUAL_REVIEW_REQUIRED, reasons=("CONTRADICTORY_HISTORY_COUNT",))
    if _contains_forbidden(comparisons):
        return _result(population, history_count, outcome=MANUAL_REVIEW_REQUIRED, reasons=("FORBIDDEN_REVIEW_INPUT",))
    if official_semantics_status not in {SEMANTICS_PENDING, SEMANTICS_CONFIRMED}:
        return _result(population, history_count, outcome=MANUAL_REVIEW_REQUIRED, reasons=("UNKNOWN_SEMANTICS_STATUS",))
    timestamps: list[str] = []
    retentions: list[float] = []
    source_sort, offset, hits = population
    for value in comparisons:
        if not isinstance(value, Mapping) or set(value) != COMPARISON_FIELDS:
            return _result(population, history_count, outcome=HOLD_FOR_ANOMALY, reasons=("MALFORMED_COMPARISON",))
        timestamp = value["captured_at"]
        if not isinstance(timestamp, str):
            return _result(population, history_count, outcome=HOLD_FOR_ANOMALY, reasons=("MALFORMED_COMPARISON",))
        timestamps.append(timestamp)
        if value["observation_band"] not in ALLOWED_BANDS:
            return _result(population, history_count, outcome=HOLD_FOR_ANOMALY, reasons=("UNKNOWN_OBSERVATION_BAND",))
        if value["classification"] != OBSERVATION_ONLY or value["production_readiness"] != REVIEW_ELIGIBLE:
            return _result(population, history_count, outcome=NOT_REVIEW_ELIGIBLE, reasons=("COMPARISON_NOT_REVIEW_ELIGIBLE",))
        hours = value["interval_hours"]
        try:
            previous_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
            current_at = previous_at + timedelta(hours=float(hours))
        except (TypeError, ValueError, OverflowError):
            return _result(population, history_count, outcome=HOLD_FOR_ANOMALY, reasons=("MALFORMED_COMPARISON",))
        previous = value["previous_count"]
        current = value["current_count"]
        retained = value["retained_count"]
        entered = value["entered_count"]
        exited = value["exited_count"]
        entry_rate = entered / current if isinstance(entered, int) and isinstance(current, int) and current else None
        exit_rate = exited / previous if isinstance(exited, int) and isinstance(previous, int) and previous else None
        assessment = assess_temporal_stability(StabilityInput(
            source_sort, offset, hits, previous_at, current_at,
            previous, current, retained, entered, exited,
            value["retention_rate"], entry_rate, exit_rate, value["jaccard"],
            value["turnover_rate"], True, history_count,
        ))
        if assessment.classification != OBSERVATION_ONLY:
            return _result(population, history_count, outcome=HOLD_FOR_ANOMALY, reasons=(assessment.safe_reason_codes or ("COMPARISON_ANOMALY",)))
        expected_band = LOW if value["retention_rate"] < .5 else MODERATE if value["retention_rate"] < .8 else HIGH
        if value["observation_band"] != expected_band:
            return _result(population, history_count, outcome=HOLD_FOR_ANOMALY, reasons=("OBSERVATION_BAND_MISMATCH",))
        retentions.append(float(value["retention_rate"]))
    if len(set(timestamps)) != len(timestamps):
        return _result(population, history_count, outcome=HOLD_FOR_ANOMALY, reasons=("DUPLICATE_COMPARISON_TIMESTAMP",))
    if not _collection_still_blocked(source_sort):
        return _result(population, history_count, outcome=MANUAL_REVIEW_REQUIRED, reasons=("COLLECTION_POLICY_BOUNDARY_VIOLATION",))
    sort_blocker = blocker_for(SORT_BLOCKER)
    if official_semantics_status == SEMANTICS_PENDING and sort_blocker.status != PENDING_OFFICIAL_CONFIRMATION:
        return _result(population, history_count, outcome=MANUAL_REVIEW_REQUIRED, reasons=("SEMANTICS_STATE_CONTRADICTION",))
    low, high = min(retentions), max(retentions)
    spread = round(high - low, 6)
    if spread > CONSISTENCY_THRESHOLD:
        return _result(
            population, history_count, eligible=True, consistency=VARIABLE,
            retention_min=low, retention_max=high, retention_range=spread,
            outcome=INSUFFICIENT_CONSISTENCY, reasons=("RETENTION_RANGE_VARIABLE",),
            semantics=official_semantics_status,
        )
    reasons = ("INTERNAL_TECHNICAL_CANDIDATE_ONLY",)
    if official_semantics_status == SEMANTICS_PENDING:
        reasons += ("OFFICIAL_SORT_SEMANTICS_PENDING", "PUBLIC_INTERPRETATION_FORBIDDEN")
    return _result(
        population, history_count, eligible=True, consistency=ACCEPTABLE,
        retention_min=low, retention_max=high, retention_range=spread,
        outcome=INTERNAL_CANDIDATE, promotion=True,
        reasons=reasons, semantics=official_semantics_status,
    )


def review_temporal_population(**kwargs: Any) -> ManualReviewResult:
    """Return safe manual-review metadata and fail closed on all exceptions."""

    try:
        return _review(**kwargs)
    except Exception:
        return _result(None, None, outcome=MANUAL_REVIEW_REQUIRED, reasons=("INTERNAL_REVIEW_ERROR",))


__all__ = [
    "ACCEPTABLE", "CONSISTENCY_THRESHOLD", "CONTINUE_OBSERVATION",
    "HOLD_FOR_ANOMALY", "HOLD_FOR_OFFICIAL_SEMANTICS", "INSUFFICIENT_CONSISTENCY",
    "INTERNAL_CANDIDATE", "MANUAL_REVIEW_REQUIRED", "ManualReviewResult",
    "NOT_REVIEW_ELIGIBLE", "OUTCOMES", "REVIEW_POLICY_VERSION",
    "SEMANTICS_CONFIRMED", "SEMANTICS_PENDING", "UNKNOWN", "VARIABLE",
    "review_temporal_population",
]
