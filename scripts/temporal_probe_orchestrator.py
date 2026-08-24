"""Safe four-population orchestration for temporal probe captures.

The orchestrator owns sequencing, stop-on-error, and aggregate-only reporting.
Response validation, anonymous state creation, comparison, and persistence stay
in the existing adapter, runner, temporal state, and state store modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import time
from typing import Any, Callable

from temporal_probe_adapter import (
    ProbeRequest,
    SafePopulationResult,
    adapt_response,
    build_request_plan,
)
from temporal_probe_runner import RunnerResult, run_temporal_probe
from temporal_probe_state import parse_timestamp
import temporal_probe_state_store as state_store


RETRY_COUNT = 0
PARTIAL_SUCCESS_POLICY = "PRESERVE_COMPLETED_STATES_STOP_REMAINING"
SAFE_REASON = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
STORE_REASONS = frozenset(
    {
        "CONCURRENT_WRITE_CONFLICT",
        "INTERNAL_STORE_ERROR",
        "OUTPUT_DIRECTORY_UNAVAILABLE",
        "STATE_CONFLICT",
        "SYMLINK_OUTPUT_FORBIDDEN",
        "SYMLINK_TARGET_FORBIDDEN",
        "UNSAFE_OUTPUT_DIRECTORY",
    }
)
READ_BACK_REASONS = frozenset(
    {"READ_BACK_INVALID", "READ_BACK_VALIDATION_FAILED"}
)
AMBIGUITY_REASONS = frozenset(
    {"AMBIGUOUS_PREVIOUS_STATE", "PREVIOUS_STATE_AMBIGUITY"}
)


@dataclass(frozen=True)
class PopulationSummary:
    source_sort: str
    offset: int
    hits: int
    success: bool | None
    result_count: int | None = None
    total_count: int | None = None
    returned_count: int | None = None
    elapsed_ms: int | None = None
    review_average_coverage: int | None = None
    review_count_coverage: int | None = None
    metadata_coverage: int | None = None
    duplicate_count: int | None = None
    state_saved: bool = False
    state_filename: str | None = None
    reason: str | None = None
    comparison_available: bool = False
    previous_captured_at: str | None = None
    current_captured_at: str | None = None
    previous_count: int | None = None
    current_count: int | None = None
    retained_count: int | None = None
    entered_count: int | None = None
    exited_count: int | None = None
    retention_rate: float | None = None
    entry_rate: float | None = None
    exit_rate: float | None = None
    jaccard: float | None = None
    turnover_rate: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class OrchestratorResult:
    overall_status: str
    planned_count: int
    executed_count: int
    succeeded_count: int
    failed_count: int
    skipped_count: int
    stopped_early: bool
    stop_reason_code: str | None
    retry_count: int
    stop_on_error: bool
    partial_success_policy: str
    populations: tuple[PopulationSummary, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **{key: value for key, value in self.__dict__.items() if key != "populations"},
            "populations": [value.to_dict() for value in self.populations],
        }


def _fixed_reason(value: Any, fallback: str) -> str:
    if isinstance(value, str) and SAFE_REASON.fullmatch(value):
        return value
    return fallback


def _runner_failure_reason(result: RunnerResult | None) -> str:
    if result is None or not isinstance(result.reason_codes, tuple):
        return "RUNNER_FAILURE"
    reasons = frozenset(result.reason_codes)
    if reasons & AMBIGUITY_REASONS:
        return "PREVIOUS_STATE_AMBIGUITY"
    if reasons & READ_BACK_REASONS:
        return "READ_BACK_VALIDATION_FAILURE"
    if reasons & STORE_REASONS:
        return "STORE_FAILURE"
    return "RUNNER_FAILURE"


def _saved_filename(
    request: ProbeRequest,
    runner_result: RunnerResult,
    *,
    output_directory: Path,
    as_of: datetime,
) -> str | None:
    captured_at = parse_timestamp(runner_result.captured_at)
    if captured_at is None:
        return None
    matches = [
        state
        for state in state_store.discover_valid_states(
            output_directory=output_directory, as_of=as_of
        )
        if state.population_identity
        == (
            request.site,
            request.service,
            request.floor,
            request.source_sort,
            request.offset,
            request.hits,
        )
        and state.captured_at == captured_at
    ]
    if len(matches) != 1:
        return None
    filename = state_store.safe_state_filename(matches[0])
    return Path(filename).name if Path(filename).name == filename else None


def _summary(
    request: ProbeRequest,
    adapted: SafePopulationResult,
    runner_result: RunnerResult | None,
    *,
    output_directory: Path,
    as_of: datetime,
) -> PopulationSummary:
    reason = _fixed_reason(
        adapted.reason_codes[0] if adapted.reason_codes else None,
        "ADAPTER_FAILURE",
    )
    if not adapted.success:
        reason = (
            _runner_failure_reason(runner_result)
            if runner_result is not None
            else reason
        )
    filename = None
    if adapted.success and adapted.state_saved and runner_result is not None:
        filename = _saved_filename(
            request, runner_result, output_directory=output_directory, as_of=as_of
        )
        if filename is None:
            reason = "STATE_FILENAME_UNAVAILABLE"
    success = adapted.success and (not adapted.state_saved or filename is not None)
    if success and runner_result is not None:
        reason = _fixed_reason(
            runner_result.reason_codes[0] if runner_result.reason_codes else None,
            "COMPARISON_CREATED",
        )
    return PopulationSummary(
        source_sort=request.source_sort,
        offset=request.offset,
        hits=request.hits,
        success=success,
        result_count=adapted.result_count,
        total_count=adapted.total_count,
        returned_count=adapted.returned_count,
        elapsed_ms=adapted.elapsed_ms,
        review_average_coverage=adapted.review_average_coverage,
        review_count_coverage=adapted.review_count_coverage,
        metadata_coverage=adapted.metadata_coverage,
        duplicate_count=adapted.duplicate_count,
        state_saved=adapted.state_saved,
        state_filename=filename,
        reason=reason,
        comparison_available=(
            runner_result.comparison_available if runner_result is not None else False
        ),
        previous_captured_at=(
            runner_result.previous_captured_at if runner_result is not None else None
        ),
        current_captured_at=(
            runner_result.captured_at if runner_result is not None else None
        ),
        previous_count=runner_result.previous_count if runner_result is not None else None,
        current_count=runner_result.current_count if runner_result is not None else None,
        retained_count=runner_result.retained_count if runner_result is not None else None,
        entered_count=runner_result.entered_count if runner_result is not None else None,
        exited_count=runner_result.exited_count if runner_result is not None else None,
        retention_rate=runner_result.retention_rate if runner_result is not None else None,
        entry_rate=runner_result.entry_rate if runner_result is not None else None,
        exit_rate=runner_result.exit_rate if runner_result is not None else None,
        jaccard=runner_result.jaccard if runner_result is not None else None,
        turnover_rate=runner_result.turnover_rate if runner_result is not None else None,
    )


def run_orchestrator(
    *,
    captured_at: datetime,
    as_of: datetime,
    fetch_response: Callable[[ProbeRequest], Any] | None = None,
    runner: Callable[..., RunnerResult] = run_temporal_probe,
    output_directory: Path = state_store.DEFAULT_STATE_DIRECTORY,
    request_delay_seconds: float = 1.0,
    delay: Callable[[float], None] = time.sleep,
    dry_run: bool = False,
) -> OrchestratorResult:
    """Run the fixed plan sequentially and return aggregate-only results."""

    plan = build_request_plan(request_delay_seconds)
    if dry_run:
        populations = tuple(
            PopulationSummary(
                request.source_sort,
                request.offset,
                request.hits,
                None,
                reason="DRY_RUN_NOT_EXECUTED",
            )
            for request in plan.requests
        )
        return OrchestratorResult(
            "DRY_RUN", len(plan.requests), 0, 0, 0, len(plan.requests), False,
            None, RETRY_COUNT, True, PARTIAL_SUCCESS_POLICY, populations,
        )

    summaries: list[PopulationSummary] = []
    stop_reason: str | None = None
    try:
        if fetch_response is None or not callable(runner) or not callable(delay):
            raise ValueError("missing execution dependency")
        for index, request in enumerate(plan.requests):
            if index:
                delay(plan.request_delay_seconds)
            captured_runner: list[RunnerResult] = []

            def observing_runner(value: Any, **kwargs: Any) -> RunnerResult:
                result = runner(value, **kwargs)
                if isinstance(result, RunnerResult):
                    captured_runner.append(result)
                return result

            try:
                response = fetch_response(request)
                adapted = adapt_response(
                    response,
                    request,
                    captured_at=captured_at,
                    as_of=as_of,
                    runner=observing_runner,
                    output_directory=output_directory,
                )
                runner_result = captured_runner[-1] if captured_runner else None
                summary = _summary(
                    request,
                    adapted,
                    runner_result,
                    output_directory=output_directory,
                    as_of=as_of,
                )
            except Exception:
                summary = PopulationSummary(
                    request.source_sort,
                    request.offset,
                    request.hits,
                    False,
                    reason="INTERNAL_ORCHESTRATOR_ERROR",
                )
            summaries.append(summary)
            if not summary.success:
                stop_reason = summary.reason or "ORCHESTRATOR_FAILURE"
                break
    except Exception:
        request = plan.requests[len(summaries)] if len(summaries) < len(plan.requests) else None
        if request is not None:
            summaries.append(
                PopulationSummary(
                    request.source_sort,
                    request.offset,
                    request.hits,
                    False,
                    reason="INTERNAL_ORCHESTRATOR_ERROR",
                )
            )
        stop_reason = "INTERNAL_ORCHESTRATOR_ERROR"

    succeeded = sum(value.success is True for value in summaries)
    failed = sum(value.success is False for value in summaries)
    skipped = len(plan.requests) - len(summaries)
    if failed:
        overall = "PARTIAL_FAILURE" if succeeded else "FAILURE"
    else:
        overall = "SUCCESS"
    return OrchestratorResult(
        overall,
        len(plan.requests),
        len(summaries),
        succeeded,
        failed,
        skipped,
        failed > 0,
        stop_reason,
        RETRY_COUNT,
        True,
        PARTIAL_SUCCESS_POLICY,
        tuple(summaries),
    )


__all__ = [
    "OrchestratorResult",
    "PARTIAL_SUCCESS_POLICY",
    "PopulationSummary",
    "RETRY_COUNT",
    "run_orchestrator",
]
