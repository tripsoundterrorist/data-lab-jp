"""Dry-run-only v0.2 temporal series runner candidate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Iterable

import temporal_probe_series_dry_run as dry_run
import temporal_probe_series_state_store_candidate as store


RUNNER_CANDIDATE_VERSION = "0.2-candidate"
RUNNER_PLAN_READY = "RUNNER_PLAN_READY"
RUNNER_BLOCKED = "RUNNER_BLOCKED"


@dataclass(frozen=True)
class SeriesRunnerCandidateResult:
    version: str
    status: str
    success: bool
    assessment_status: str | None
    comparison_available: bool
    stability_classification: str | None
    production_readiness: str | None
    previous_count: int | None
    current_count: int | None
    retained_count: int | None
    entered_count: int | None
    exited_count: int | None
    write_plan_status: str | None
    write_plan_created: bool
    filesystem_access_performed: bool
    active_runner_connected: bool
    api_request_authorized: bool
    state_write_authorized: bool
    baseline_activation_authorized: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(code: str) -> SeriesRunnerCandidateResult:
    return SeriesRunnerCandidateResult(
        RUNNER_CANDIDATE_VERSION, RUNNER_BLOCKED, False,
        None, False, None, None, None, None, None, None, None,
        None, False, False, False, False, False, False, (code,),
    )


def run_temporal_series_candidate(
    current: Any,
    documents: Iterable[Any],
    *,
    as_of: datetime,
    history_count: Any,
) -> SeriesRunnerCandidateResult:
    """Assess and create a memory-only write plan; never persist state."""

    try:
        assessed = dry_run.run_series_dry_run(
            current, documents, as_of=as_of, history_count=history_count
        )
        if not isinstance(assessed, dry_run.SeriesDryRunResult):
            return _blocked("DRY_RUN_RESULT_INVALID")
        if not assessed.success:
            return _blocked("SERIES_ASSESSMENT_BLOCKED")
        planned = store.plan_series_state_write(current, as_of=as_of)
        if (
            not isinstance(planned, store.SeriesStateWritePlan)
            or not planned.success
            or planned.status != store.WRITE_PLAN_READY
            or planned.filesystem_access_performed
            or planned.state_write_authorized
        ):
            return _blocked("SERIES_WRITE_PLAN_BLOCKED")
        return SeriesRunnerCandidateResult(
            RUNNER_CANDIDATE_VERSION,
            RUNNER_PLAN_READY,
            True,
            assessed.status,
            assessed.comparison_available,
            assessed.stability_classification,
            assessed.production_readiness,
            assessed.previous_count,
            assessed.current_count,
            assessed.retained_count,
            assessed.entered_count,
            assessed.exited_count,
            planned.status,
            True,
            False,
            False,
            False,
            False,
            False,
            ("DRY_RUN_ONLY", "MEMORY_ONLY_WRITE_PLAN"),
        )
    except Exception:
        return _blocked("SERIES_RUNNER_CANDIDATE_ERROR")


__all__ = [
    "RUNNER_BLOCKED", "RUNNER_CANDIDATE_VERSION", "RUNNER_PLAN_READY",
    "SeriesRunnerCandidateResult", "run_temporal_series_candidate",
]
