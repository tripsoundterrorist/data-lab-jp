"""Pure four-population orchestrator for temporal series dry runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

import temporal_probe_series_dry_run as dry_run
import temporal_probe_series_state as series_state
from temporal_runbook_policy import FIXED_POPULATIONS


ORCHESTRATOR_VERSION = "0.1"
DRY_RUN_COMPLETE = "DRY_RUN_COMPLETE"
DRY_RUN_BLOCKED = "DRY_RUN_BLOCKED"

@dataclass(frozen=True)
class PopulationDryRunSummary:
    source_sort: str
    offset: int
    hits: int
    status: str
    success: bool | None
    comparison_available: bool
    stability_classification: str | None
    production_readiness: str | None
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


@dataclass(frozen=True)
class SeriesDryOrchestratorResult:
    version: str
    status: str
    success: bool
    planned_count: int
    evaluated_count: int
    succeeded_count: int
    failed_count: int
    skipped_count: int
    stop_on_error: bool
    api_request_authorized: bool
    state_write_authorized: bool
    baseline_activation_authorized: bool
    populations: tuple[PopulationDryRunSummary, ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["populations"] = [item.to_dict() for item in self.populations]
        value["reason_codes"] = list(self.reason_codes)
        return value


def _not_run(identity: tuple[str, int, int]) -> PopulationDryRunSummary:
    return PopulationDryRunSummary(
        *identity, "NOT_RUN", None, False, None, None,
        ("STOP_ON_FIRST_ERROR",),
    )


def _failure(reason: str) -> SeriesDryOrchestratorResult:
    return SeriesDryOrchestratorResult(
        ORCHESTRATOR_VERSION, DRY_RUN_BLOCKED, False,
        len(FIXED_POPULATIONS), 0, 0, 0, len(FIXED_POPULATIONS), True,
        False, False, False,
        tuple(_not_run(identity) for identity in FIXED_POPULATIONS),
        (reason,),
    )


def run_fixed_series_dry_orchestrator(
    *,
    current_states: Sequence[Any],
    documents_by_population: Mapping[tuple[str, int, int], Sequence[Any]],
    history_counts: Mapping[tuple[str, int, int], Any],
    as_of: datetime,
) -> SeriesDryOrchestratorResult:
    """Evaluate the exact fixed order and stop after the first blocked result."""

    try:
        if (
            not isinstance(current_states, Sequence)
            or isinstance(current_states, (str, bytes))
            or len(current_states) != len(FIXED_POPULATIONS)
            or not isinstance(documents_by_population, Mapping)
            or set(documents_by_population) != set(FIXED_POPULATIONS)
            or not isinstance(history_counts, Mapping)
            or set(history_counts) != set(FIXED_POPULATIONS)
        ):
            return _failure("FIXED_DRY_RUN_INPUT_INVALID")
        summaries: list[PopulationDryRunSummary] = []
        stopped = False
        for identity, current in zip(FIXED_POPULATIONS, current_states):
            if stopped:
                summaries.append(_not_run(identity))
                continue
            validation = series_state.validate_temporal_probe_series_state(
                current, as_of=as_of
            )
            actual_identity = (
                current.legacy_state.source_sort,
                current.legacy_state.offset,
                current.legacy_state.hits,
            ) if validation.valid else None
            if actual_identity != identity:
                return _failure("CURRENT_STATE_ORDER_OR_IDENTITY_INVALID")
            result = dry_run.run_series_dry_run(
                current,
                documents_by_population[identity],
                as_of=as_of,
                history_count=history_counts[identity],
            )
            summaries.append(
                PopulationDryRunSummary(
                    *identity,
                    result.status,
                    result.success,
                    result.comparison_available,
                    result.stability_classification,
                    result.production_readiness,
                    result.reason_codes,
                )
            )
            if not result.success:
                stopped = True
        succeeded = sum(item.success is True for item in summaries)
        failed = sum(item.success is False for item in summaries)
        skipped = sum(item.success is None for item in summaries)
        complete = succeeded == len(FIXED_POPULATIONS)
        return SeriesDryOrchestratorResult(
            ORCHESTRATOR_VERSION,
            DRY_RUN_COMPLETE if complete else DRY_RUN_BLOCKED,
            complete,
            len(FIXED_POPULATIONS),
            succeeded + failed,
            succeeded,
            failed,
            skipped,
            True,
            False,
            False,
            False,
            tuple(summaries),
            ("DRY_RUN_ONLY",) if complete else ("STOPPED_FAIL_CLOSED",),
        )
    except Exception:
        return _failure("SERIES_DRY_ORCHESTRATOR_ERROR")


__all__ = [
    "DRY_RUN_BLOCKED", "DRY_RUN_COMPLETE", "ORCHESTRATOR_VERSION",
    "PopulationDryRunSummary", "SeriesDryOrchestratorResult",
    "run_fixed_series_dry_orchestrator",
]
