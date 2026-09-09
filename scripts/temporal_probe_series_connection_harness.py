"""Four-population dry-run harness for the isolated v0.2 runner candidate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

import temporal_probe_series_runner_candidate as runner
import temporal_probe_series_state as series
from temporal_runbook_policy import FIXED_POPULATIONS


HARNESS_VERSION = "0.1-candidate"
HARNESS_COMPLETE = "DRY_CONNECTION_HARNESS_COMPLETE"
HARNESS_BLOCKED = "DRY_CONNECTION_HARNESS_BLOCKED"


@dataclass(frozen=True)
class PopulationHarnessSummary:
    source_sort: str
    offset: int
    hits: int
    status: str
    success: bool | None
    comparison_available: bool
    write_plan_created: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


@dataclass(frozen=True)
class SeriesConnectionHarnessResult:
    version: str
    status: str
    success: bool
    evaluated_count: int
    succeeded_count: int
    failed_count: int
    skipped_count: int
    stop_on_error: bool
    active_pipeline_connected: bool
    filesystem_access_performed: bool
    api_request_authorized: bool
    state_write_authorized: bool
    baseline_activation_authorized: bool
    populations: tuple[PopulationHarnessSummary, ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["populations"] = [item.to_dict() for item in self.populations]
        value["reason_codes"] = list(self.reason_codes)
        return value


def _not_run(identity):
    return PopulationHarnessSummary(
        *identity, "NOT_RUN", None, False, False, ("STOP_ON_FIRST_ERROR",)
    )


def _blocked(code):
    return SeriesConnectionHarnessResult(
        HARNESS_VERSION, HARNESS_BLOCKED, False, 0, 0, 0,
        len(FIXED_POPULATIONS), True, False, False, False, False, False,
        tuple(_not_run(identity) for identity in FIXED_POPULATIONS), (code,),
    )


def run_dry_connection_harness(
    *, current_states: Sequence[Any],
    documents_by_population: Mapping[tuple[str, int, int], Sequence[Any]],
    history_counts: Mapping[tuple[str, int, int], Any],
    as_of: datetime,
) -> SeriesConnectionHarnessResult:
    """Run the candidate chain in fixed order without connecting active code."""
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
            return _blocked("FIXED_HARNESS_INPUT_INVALID")
        for identity, current in zip(FIXED_POPULATIONS, current_states):
            valid = series.validate_temporal_probe_series_state(
                current, as_of=as_of
            ).valid
            actual = (
                current.legacy_state.source_sort,
                current.legacy_state.offset,
                current.legacy_state.hits,
            ) if valid else None
            if actual != identity:
                return _blocked("CURRENT_STATE_ORDER_OR_IDENTITY_INVALID")

        summaries = []
        stopped = False
        for identity, current in zip(FIXED_POPULATIONS, current_states):
            if stopped:
                summaries.append(_not_run(identity))
                continue
            result = runner.run_temporal_series_candidate(
                current, documents_by_population[identity], as_of=as_of,
                history_count=history_counts[identity],
            )
            success = isinstance(
                result, runner.SeriesRunnerCandidateResult
            ) and result.success
            summaries.append(PopulationHarnessSummary(
                *identity,
                result.status if isinstance(
                    result, runner.SeriesRunnerCandidateResult
                ) else runner.RUNNER_BLOCKED,
                success,
                result.comparison_available if success else False,
                result.write_plan_created if success else False,
                result.reason_codes if success else ("RUNNER_CANDIDATE_BLOCKED",),
            ))
            if not success:
                stopped = True
        succeeded = sum(item.success is True for item in summaries)
        failed = sum(item.success is False for item in summaries)
        skipped = sum(item.success is None for item in summaries)
        complete = succeeded == len(FIXED_POPULATIONS)
        return SeriesConnectionHarnessResult(
            HARNESS_VERSION,
            HARNESS_COMPLETE if complete else HARNESS_BLOCKED,
            complete, succeeded + failed, succeeded, failed, skipped, True,
            False, False, False, False, False, tuple(summaries),
            ("ISOLATED_DRY_CONNECTION_ONLY",) if complete
            else ("STOPPED_FAIL_CLOSED",),
        )
    except Exception:
        return _blocked("DRY_CONNECTION_HARNESS_ERROR")


__all__ = [
    "HARNESS_BLOCKED", "HARNESS_COMPLETE", "HARNESS_VERSION",
    "PopulationHarnessSummary", "SeriesConnectionHarnessResult",
    "run_dry_connection_harness",
]
