"""Safe orchestration from minimal probe results to temporal aggregates.

This module performs no API calls and emits no item identifiers. Raw content
IDs exist only while building a validated pseudonymous temporal state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from temporal_probe_state import (
    TemporalComparison,
    TemporalProbeState,
    compare_temporal_probe_states,
    create_temporal_probe_state,
    validate_temporal_probe_state,
)
import temporal_probe_state_store as state_store


PROBE_RESULT_FIELDS = frozenset(
    {
        "captured_at",
        "site",
        "service",
        "floor",
        "source_sort",
        "offset",
        "hits",
        "result_count",
        "items",
    }
)
ITEM_FIELDS = frozenset({"content_id"})


@dataclass(frozen=True)
class RunnerResult:
    success: bool
    source_sort: str | None
    offset: int | None
    hits: int | None
    captured_at: str | None
    observation_semantics: str | None
    state_saved: bool
    comparison_available: bool
    previous_captured_at: str | None
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
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "source_sort": self.source_sort,
            "offset": self.offset,
            "hits": self.hits,
            "captured_at": self.captured_at,
            "observation_semantics": self.observation_semantics,
            "state_saved": self.state_saved,
            "comparison_available": self.comparison_available,
            "previous_captured_at": self.previous_captured_at,
            "previous_count": self.previous_count,
            "current_count": self.current_count,
            "retained_count": self.retained_count,
            "entered_count": self.entered_count,
            "exited_count": self.exited_count,
            "retention_rate": self.retention_rate,
            "entry_rate": self.entry_rate,
            "exit_rate": self.exit_rate,
            "jaccard": self.jaccard,
            "turnover_rate": self.turnover_rate,
            "reason_codes": list(self.reason_codes),
        }


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _empty_result(
    *,
    success: bool,
    reason_codes: tuple[str, ...],
    state: TemporalProbeState | None = None,
    state_saved: bool = False,
) -> RunnerResult:
    source_sort = state.source_sort if state is not None else None
    return RunnerResult(
        success=success,
        source_sort=source_sort,
        offset=state.offset if state is not None else None,
        hits=state.hits if state is not None else None,
        captured_at=_timestamp(state.captured_at) if state is not None else None,
        observation_semantics=(
            f"{source_sort}-sorted population turnover" if source_sort else None
        ),
        state_saved=state_saved,
        comparison_available=False,
        previous_captured_at=None,
        previous_count=None,
        current_count=state.returned_count if state is not None else None,
        retained_count=None,
        entered_count=None,
        exited_count=None,
        retention_rate=None,
        entry_rate=None,
        exit_rate=None,
        jaccard=None,
        turnover_rate=None,
        reason_codes=reason_codes,
    )


def _state_from_probe_result(value: Any) -> TemporalProbeState:
    if not isinstance(value, Mapping) or set(value) != PROBE_RESULT_FIELDS:
        raise ValueError("invalid probe contract")
    source_sort = value["source_sort"]
    if source_sort not in {"rank", "review"}:
        raise ValueError("unsupported sort")
    items = value["items"]
    result_count = value["result_count"]
    if (
        not isinstance(items, list)
        or isinstance(result_count, bool)
        or not isinstance(result_count, int)
        or result_count < 0
        or result_count != len(items)
    ):
        raise ValueError("invalid result count")
    content_ids: list[str] = []
    for item in items:
        if not isinstance(item, Mapping) or set(item) != ITEM_FIELDS:
            raise ValueError("invalid item contract")
        content_id = item["content_id"]
        if not isinstance(content_id, str):
            raise ValueError("invalid source identifier")
        content_ids.append(content_id)
    if len(set(content_ids)) != len(content_ids):
        raise ValueError("duplicate source identifier")
    return create_temporal_probe_state(
        captured_at=value["captured_at"],
        site=value["site"],
        service=value["service"],
        floor=value["floor"],
        source_sort=source_sort,
        offset=value["offset"],
        hits=value["hits"],
        content_ids=content_ids,
    )


def _comparison_result(
    state: TemporalProbeState,
    previous: TemporalProbeState,
    comparison: TemporalComparison,
    *,
    state_saved: bool,
    dry_run: bool,
) -> RunnerResult:
    return RunnerResult(
        success=True,
        source_sort=state.source_sort,
        offset=state.offset,
        hits=state.hits,
        captured_at=_timestamp(state.captured_at),
        observation_semantics=f"{state.source_sort}-sorted population turnover",
        state_saved=state_saved,
        comparison_available=True,
        previous_captured_at=_timestamp(previous.captured_at),
        previous_count=comparison.previous_count,
        current_count=comparison.current_count,
        retained_count=comparison.retained_count,
        entered_count=comparison.entered_count,
        exited_count=comparison.exited_count,
        retention_rate=comparison.retention_rate,
        entry_rate=comparison.entry_rate,
        exit_rate=comparison.exit_rate,
        jaccard=comparison.jaccard,
        turnover_rate=comparison.turnover_rate,
        reason_codes=("DRY_RUN",) if dry_run else (),
    )


def run_temporal_probe(
    probe_result: Any,
    *,
    as_of: datetime,
    dry_run: bool = False,
    output_directory: Path = state_store.DEFAULT_STATE_DIRECTORY,
) -> RunnerResult:
    """Validate, compare, then persist; never return identifier collections."""

    try:
        if not isinstance(dry_run, bool):
            return _empty_result(
                success=False, reason_codes=("INVALID_DRY_RUN_FLAG",)
            )
        state = _state_from_probe_result(probe_result)
        validation = validate_temporal_probe_state(state, as_of=as_of)
        if not validation.valid:
            return _empty_result(
                success=False, reason_codes=validation.reason_codes, state=state
            )

        discovery = state_store.latest_previous_state(
            state, output_directory=output_directory, as_of=as_of
        )
        if not discovery.success:
            return _empty_result(
                success=False, reason_codes=discovery.reason_codes, state=state
            )

        previous = discovery.state
        comparison: TemporalComparison | None = None
        if previous is not None:
            comparison = compare_temporal_probe_states(
                previous, state, as_of=as_of
            )
            if not comparison.comparison_valid:
                return _empty_result(
                    success=False,
                    reason_codes=comparison.reason_codes,
                    state=state,
                )

        if dry_run:
            plan = state_store.plan_state_write(
                state, output_directory=output_directory
            )
            if not plan.success:
                return _empty_result(
                    success=False, reason_codes=plan.reason_codes, state=state
                )
            if previous is None or comparison is None:
                return _empty_result(
                    success=True,
                    reason_codes=("DRY_RUN_BASELINE_PLANNED",),
                    state=state,
                )
            return _comparison_result(
                state,
                previous,
                comparison,
                state_saved=False,
                dry_run=True,
            )

        stored = state_store.write_temporal_probe_state(
            state, output_directory=output_directory
        )
        if not stored.success:
            return _empty_result(
                success=False, reason_codes=stored.reason_codes, state=state
            )
        if previous is None or comparison is None:
            return _empty_result(
                success=True,
                reason_codes=("BASELINE_CREATED",),
                state=state,
                state_saved=True,
            )
        return _comparison_result(
            state,
            previous,
            comparison,
            state_saved=True,
            dry_run=False,
        )
    except Exception:
        return _empty_result(
            success=False, reason_codes=("INTERNAL_RUNNER_ERROR",)
        )


__all__ = ["PROBE_RESULT_FIELDS", "RunnerResult", "run_temporal_probe"]
