"""Pure assessment policy for temporal query-population comparisons.

This module validates aggregate metrics only.  It has no API, filesystem, or
database access and assigns no business, demand, sales, or ranking meaning.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Any


POLICY_VERSION = "0.1"
MIN_MEANINGFUL_INTERVAL_HOURS = 12.0
MAX_MEANINGFUL_INTERVAL_HOURS = 48.0
MIN_COMPARISONS_FOR_STABILITY_REVIEW = 3
RATE_TOLERANCE = 0.000001
ALLOWED_POPULATIONS = frozenset(
    {
        ("rank", 1, 100),
        ("rank", 101, 100),
        ("review", 1, 100),
        ("review", 101, 100),
    }
)

INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
OBSERVATION_ONLY = "OBSERVATION_ONLY"
ANOMALOUS_COMPARISON = "ANOMALOUS_COMPARISON"
INVALID_INPUT = "INVALID_INPUT"

LOW = "LOW"
MODERATE = "MODERATE"
HIGH = "HIGH"
UNKNOWN = "UNKNOWN"

NOT_EVALUATED = "NOT_EVALUATED"
REVIEW_ELIGIBLE = "REVIEW_ELIGIBLE"


@dataclass(frozen=True)
class StabilityInput:
    source_sort: str
    offset: int
    hits: int
    previous_captured_at: datetime | str | None
    current_captured_at: datetime | str | None
    previous_count: int | None
    current_count: int | None
    retained_count: int | None
    entered_count: int | None
    exited_count: int | None
    retention_rate: float | None
    entry_rate: float | None
    exit_rate: float | None
    jaccard: float | None
    turnover_rate: float | None
    comparison_available: bool
    history_count: int


@dataclass(frozen=True)
class StabilityAssessment:
    policy_version: str
    source_sort: str | None
    offset: int | None
    hits: int | None
    comparison_available: bool
    interval_seconds: int | None
    interval_hours: float | None
    previous_count: int | None
    current_count: int | None
    retained_count: int | None
    entered_count: int | None
    exited_count: int | None
    retention_rate: float | None
    jaccard: float | None
    turnover_rate: float | None
    population_complete: bool | None
    observation_band: str
    classification: str
    production_readiness: str
    safe_reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **{
                key: value
                for key, value in self.__dict__.items()
                if key != "safe_reason_codes"
            },
            "safe_reason_codes": list(self.safe_reason_codes),
        }


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _rate_value(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and 0.0 <= float(value) <= 1.0
    )


def _matches(value: float, numerator: int, denominator: int) -> bool:
    expected = round(numerator / denominator, 6)
    return math.isclose(float(value), expected, rel_tol=0.0, abs_tol=RATE_TOLERANCE)


def _result(
    value: StabilityInput | None,
    *,
    classification: str,
    observation_band: str = UNKNOWN,
    production_readiness: str = NOT_EVALUATED,
    reasons: tuple[str, ...],
    interval_seconds: int | None = None,
    interval_hours: float | None = None,
    population_complete: bool | None = None,
) -> StabilityAssessment:
    return StabilityAssessment(
        policy_version=POLICY_VERSION,
        source_sort=value.source_sort if isinstance(value, StabilityInput) else None,
        offset=value.offset if isinstance(value, StabilityInput) else None,
        hits=value.hits if isinstance(value, StabilityInput) else None,
        comparison_available=(
            value.comparison_available if isinstance(value, StabilityInput) and isinstance(value.comparison_available, bool) else False
        ),
        interval_seconds=interval_seconds,
        interval_hours=interval_hours,
        previous_count=value.previous_count if isinstance(value, StabilityInput) else None,
        current_count=value.current_count if isinstance(value, StabilityInput) else None,
        retained_count=value.retained_count if isinstance(value, StabilityInput) else None,
        entered_count=value.entered_count if isinstance(value, StabilityInput) else None,
        exited_count=value.exited_count if isinstance(value, StabilityInput) else None,
        retention_rate=value.retention_rate if isinstance(value, StabilityInput) else None,
        jaccard=value.jaccard if isinstance(value, StabilityInput) else None,
        turnover_rate=value.turnover_rate if isinstance(value, StabilityInput) else None,
        population_complete=population_complete,
        observation_band=observation_band,
        classification=classification,
        production_readiness=production_readiness,
        safe_reason_codes=reasons,
    )


def _assess(value: Any) -> StabilityAssessment:
    if not isinstance(value, StabilityInput):
        return _result(None, classification=INVALID_INPUT, reasons=("MALFORMED_INPUT",))
    if (
        (value.source_sort, value.offset, value.hits) not in ALLOWED_POPULATIONS
        or not _integer(value.history_count)
        or value.history_count < 0
        or not isinstance(value.comparison_available, bool)
    ):
        return _result(value, classification=INVALID_INPUT, reasons=("INVALID_POPULATION_OR_HISTORY",))

    metrics = (
        value.previous_count,
        value.current_count,
        value.retained_count,
        value.entered_count,
        value.exited_count,
        value.retention_rate,
        value.entry_rate,
        value.exit_rate,
        value.jaccard,
        value.turnover_rate,
    )
    if not value.comparison_available:
        if any(metric is not None for metric in metrics):
            return _result(value, classification=INVALID_INPUT, reasons=("UNEXPECTED_COMPARISON_METRICS",))
        return _result(
            value,
            classification=INSUFFICIENT_HISTORY,
            reasons=("COMPARISON_UNAVAILABLE",),
        )
    if value.history_count < 1:
        return _result(value, classification=INVALID_INPUT, reasons=("INVALID_HISTORY_COUNT",))

    previous_at = _parse_timestamp(value.previous_captured_at)
    current_at = _parse_timestamp(value.current_captured_at)
    if previous_at is None or current_at is None:
        return _result(value, classification=INVALID_INPUT, reasons=("TIMESTAMP_INVALID",))
    if current_at <= previous_at:
        return _result(value, classification=INVALID_INPUT, reasons=("TIMESTAMP_ORDER_INVALID",))
    interval_seconds = round((current_at - previous_at).total_seconds())
    interval_hours = round(interval_seconds / 3600.0, 6)

    counts = (
        value.previous_count,
        value.current_count,
        value.retained_count,
        value.entered_count,
        value.exited_count,
    )
    if any(not _integer(count) for count in counts):
        return _result(value, classification=INVALID_INPUT, reasons=("COUNT_INVALID",), interval_seconds=interval_seconds, interval_hours=interval_hours)
    previous, current, retained, entered, exited = counts
    if previous <= 0 or current <= 0 or previous > value.hits or current > value.hits:
        return _result(value, classification=INVALID_INPUT, reasons=("POPULATION_COUNT_INVALID",), interval_seconds=interval_seconds, interval_hours=interval_hours)
    if retained < 0 or retained > previous or retained > current or entered < 0 or exited < 0:
        return _result(value, classification=ANOMALOUS_COMPARISON, reasons=("IMPOSSIBLE_COUNTS",), interval_seconds=interval_seconds, interval_hours=interval_hours)
    if entered != current - retained or exited != previous - retained:
        return _result(value, classification=ANOMALOUS_COMPARISON, reasons=("COUNT_RELATION_MISMATCH",), interval_seconds=interval_seconds, interval_hours=interval_hours)

    rates = (value.retention_rate, value.entry_rate, value.exit_rate, value.jaccard, value.turnover_rate)
    if any(not _rate_value(rate) for rate in rates):
        return _result(value, classification=INVALID_INPUT, reasons=("RATE_INVALID",), interval_seconds=interval_seconds, interval_hours=interval_hours)
    union = previous + current - retained
    consistency = (
        _matches(value.retention_rate, retained, previous),
        _matches(value.entry_rate, entered, current),
        _matches(value.exit_rate, exited, previous),
        _matches(value.jaccard, retained, union),
        _matches(value.turnover_rate, entered + exited, union),
    )
    if not all(consistency):
        return _result(value, classification=ANOMALOUS_COMPARISON, reasons=("METRIC_CONSISTENCY_MISMATCH",), interval_seconds=interval_seconds, interval_hours=interval_hours)
    if interval_hours < MIN_MEANINGFUL_INTERVAL_HOURS:
        return _result(value, classification=ANOMALOUS_COMPARISON, reasons=("INTERVAL_TOO_SHORT",), interval_seconds=interval_seconds, interval_hours=interval_hours, population_complete=(previous == value.hits and current == value.hits))
    if interval_hours > MAX_MEANINGFUL_INTERVAL_HOURS:
        return _result(value, classification=ANOMALOUS_COMPARISON, reasons=("DAY_INTERVAL_OUT_OF_RANGE",), interval_seconds=interval_seconds, interval_hours=interval_hours, population_complete=(previous == value.hits and current == value.hits))

    retention = float(value.retention_rate)
    band = LOW if retention < 0.50 else MODERATE if retention < 0.80 else HIGH
    readiness = REVIEW_ELIGIBLE if value.history_count >= MIN_COMPARISONS_FOR_STABILITY_REVIEW else NOT_EVALUATED
    return _result(
        value,
        classification=OBSERVATION_ONLY,
        observation_band=band,
        production_readiness=readiness,
        reasons=("QUERY_POPULATION_COMPOSITION_OBSERVATION",),
        interval_seconds=interval_seconds,
        interval_hours=interval_hours,
        population_complete=(previous == value.hits and current == value.hits),
    )


def assess_temporal_stability(value: Any) -> StabilityAssessment:
    """Return a safe assessment without inferring API or business semantics."""

    try:
        return _assess(value)
    except Exception:
        return _result(None, classification=INVALID_INPUT, reasons=("INTERNAL_POLICY_ERROR",))


__all__ = [
    "ALLOWED_POPULATIONS",
    "ANOMALOUS_COMPARISON",
    "HIGH",
    "INSUFFICIENT_HISTORY",
    "INVALID_INPUT",
    "LOW",
    "MAX_MEANINGFUL_INTERVAL_HOURS",
    "MIN_COMPARISONS_FOR_STABILITY_REVIEW",
    "MIN_MEANINGFUL_INTERVAL_HOURS",
    "MODERATE",
    "NOT_EVALUATED",
    "OBSERVATION_ONLY",
    "POLICY_VERSION",
    "REVIEW_ELIGIBLE",
    "StabilityAssessment",
    "StabilityInput",
    "UNKNOWN",
    "assess_temporal_stability",
]
