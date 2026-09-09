"""Pure dry-run candidate for explicit temporal observation series."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Iterable

import temporal_probe_series_discovery as discovery
import temporal_probe_series_state as series_state
from temporal_stability_policy import StabilityInput, assess_temporal_stability


DRY_RUN_VERSION = "0.1"
BASELINE_PLANNED = "EXPLICIT_SERIES_BASELINE_PLANNED"
COMPARISON_ASSESSED = "SAME_SERIES_COMPARISON_ASSESSED"
BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class SeriesDryRunResult:
    version: str
    status: str
    success: bool
    api_request_authorized: bool
    state_write_authorized: bool
    baseline_activation_authorized: bool
    comparison_available: bool
    stability_classification: str | None
    production_readiness: str | None
    previous_count: int | None
    current_count: int | None
    retained_count: int | None
    entered_count: int | None
    exited_count: int | None
    retention_rate: float | None
    jaccard: float | None
    turnover_rate: float | None
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(
    status: str,
    *,
    success: bool = False,
    comparison_available: bool = False,
    stability_classification: str | None = None,
    production_readiness: str | None = None,
    comparison: Any = None,
    reasons: tuple[str, ...],
) -> SeriesDryRunResult:
    return SeriesDryRunResult(
        DRY_RUN_VERSION,
        status,
        success,
        False,
        False,
        False,
        comparison_available,
        stability_classification,
        production_readiness,
        getattr(comparison, "previous_count", None),
        getattr(comparison, "current_count", None),
        getattr(comparison, "retained_count", None),
        getattr(comparison, "entered_count", None),
        getattr(comparison, "exited_count", None),
        getattr(comparison, "retention_rate", None),
        getattr(comparison, "jaccard", None),
        getattr(comparison, "turnover_rate", None),
        reasons,
    )


def run_series_dry_run(
    current: Any,
    documents: Iterable[Any],
    *,
    as_of: datetime,
    history_count: Any,
) -> SeriesDryRunResult:
    """Plan a baseline or assess a comparison without I/O or authorization."""

    try:
        if (
            not isinstance(history_count, int)
            or isinstance(history_count, bool)
            or history_count < 0
        ):
            return _result(BLOCKED, reasons=("INVALID_HISTORY_COUNT",))
        found = discovery.discover_latest_same_series(
            current, documents, as_of=as_of
        )
        if not found.success:
            return _result(BLOCKED, reasons=found.reason_codes)
        if found.status == discovery.EXPLICIT_BASELINE_CANDIDATE:
            if history_count != 0:
                return _result(
                    BLOCKED,
                    reasons=("BASELINE_HISTORY_COUNT_MUST_BE_ZERO",),
                )
            return _result(
                BASELINE_PLANNED,
                success=True,
                reasons=(
                    "DRY_RUN_ONLY",
                    "SEPARATE_BASELINE_ACTIVATION_REQUIRED",
                ),
            )
        if found.status != discovery.LATEST_FOUND or found.selected is None:
            return _result(BLOCKED, reasons=("DISCOVERY_STATE_INVALID",))
        if history_count < 1:
            return _result(
                BLOCKED, reasons=("COMPARISON_HISTORY_COUNT_REQUIRED",)
            )
        compared = series_state.compare_temporal_probe_series_states(
            found.selected, current, as_of=as_of
        )
        if not compared.comparison_valid:
            return _result(BLOCKED, reasons=compared.reason_codes)
        previous = found.selected.legacy_state
        candidate = current.legacy_state
        assessment = assess_temporal_stability(
            StabilityInput(
                source_sort=candidate.source_sort,
                offset=candidate.offset,
                hits=candidate.hits,
                previous_captured_at=previous.captured_at,
                current_captured_at=candidate.captured_at,
                previous_count=compared.previous_count,
                current_count=compared.current_count,
                retained_count=compared.retained_count,
                entered_count=compared.entered_count,
                exited_count=compared.exited_count,
                retention_rate=compared.retention_rate,
                entry_rate=compared.entry_rate,
                exit_rate=compared.exit_rate,
                jaccard=compared.jaccard,
                turnover_rate=compared.turnover_rate,
                comparison_available=True,
                history_count=history_count,
            )
        )
        if assessment.classification != "OBSERVATION_ONLY":
            return _result(
                BLOCKED,
                comparison_available=True,
                stability_classification=assessment.classification,
                production_readiness=assessment.production_readiness,
                comparison=compared,
                reasons=assessment.safe_reason_codes,
            )
        return _result(
            COMPARISON_ASSESSED,
            success=True,
            comparison_available=True,
            stability_classification=assessment.classification,
            production_readiness=assessment.production_readiness,
            comparison=compared,
            reasons=("DRY_RUN_ONLY",) + assessment.safe_reason_codes,
        )
    except Exception:
        return _result(BLOCKED, reasons=("SERIES_DRY_RUN_ERROR",))


__all__ = [
    "BASELINE_PLANNED", "BLOCKED", "COMPARISON_ASSESSED",
    "DRY_RUN_VERSION", "SeriesDryRunResult", "run_series_dry_run",
]
