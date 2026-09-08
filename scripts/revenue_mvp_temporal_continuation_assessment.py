"""Read-only pre-API assessment for temporal observation continuation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import temporal_probe_state_store
from temporal_probe_adapter import FLOOR, HITS, SERVICE, SITE
from temporal_runbook_policy import FIXED_POPULATIONS
from temporal_stability_policy import (
    MAX_MEANINGFUL_INTERVAL_HOURS,
    MIN_MEANINGFUL_INTERVAL_HOURS,
)


VERSION = "0.1"
WINDOW_CANDIDATE = "OBSERVATION_WINDOW_CANDIDATE"
WAIT = "WAIT_FOR_OBSERVATION_WINDOW"
LONG_GAP_BLOCKED = "LONG_GAP_BLOCKED"
FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class TemporalContinuationAssessment:
    version: str
    status: str
    observation_window_candidate: bool
    api_request_authorized: bool
    state_write_authorized: bool
    fresh_baseline_policy_required: bool
    populations_found: int
    minimum_age_hours: float | None
    maximum_age_hours: float | None
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(
    status: str,
    *,
    candidate: bool = False,
    fresh_baseline_required: bool = False,
    populations_found: int = 0,
    minimum_age_hours: float | None = None,
    maximum_age_hours: float | None = None,
    reasons: tuple[str, ...],
) -> TemporalContinuationAssessment:
    return TemporalContinuationAssessment(
        VERSION,
        status,
        candidate,
        False,
        False,
        fresh_baseline_required,
        populations_found,
        minimum_age_hours,
        maximum_age_hours,
        reasons,
    )


def assess_temporal_continuation(
    *,
    as_of: datetime,
    output_directory: Path = temporal_probe_state_store.DEFAULT_STATE_DIRECTORY,
) -> TemporalContinuationAssessment:
    """Classify latest aggregate state ages before any API or state write."""

    try:
        if (
            not isinstance(as_of, datetime)
            or as_of.tzinfo is None
            or as_of.utcoffset() is None
        ):
            raise ValueError("invalid as_of")
        normalized_as_of = as_of.astimezone(timezone.utc)
        states = temporal_probe_state_store.discover_valid_states(
            output_directory=output_directory,
            as_of=normalized_as_of,
        )
        latest: dict[tuple[str, int, int], datetime] = {}
        for source_sort, offset, hits in FIXED_POPULATIONS:
            identity = (SITE, SERVICE, FLOOR, source_sort, offset, HITS)
            candidates = [
                state.captured_at
                for state in states
                if state.population_identity == identity
            ]
            if candidates:
                latest[(source_sort, offset, hits)] = max(candidates)
        if len(latest) != len(FIXED_POPULATIONS):
            return _result(
                FAIL_CLOSED,
                populations_found=len(latest),
                reasons=("FIXED_POPULATION_STATE_INCOMPLETE",),
            )
        ages = tuple(
            (normalized_as_of - captured_at.astimezone(timezone.utc))
            .total_seconds() / 3600.0
            for captured_at in latest.values()
        )
        if any(age < 0 for age in ages):
            raise ValueError("future state")
        low = round(min(ages), 6)
        high = round(max(ages), 6)
        if all(age > MAX_MEANINGFUL_INTERVAL_HOURS for age in ages):
            return _result(
                LONG_GAP_BLOCKED,
                fresh_baseline_required=True,
                populations_found=len(latest),
                minimum_age_hours=low,
                maximum_age_hours=high,
                reasons=(
                    "PREVIOUS_STATE_OUTSIDE_COMPARISON_WINDOW",
                    "FRESH_BASELINE_POLICY_REQUIRED",
                ),
            )
        if all(age < MIN_MEANINGFUL_INTERVAL_HOURS for age in ages):
            return _result(
                WAIT,
                populations_found=len(latest),
                minimum_age_hours=low,
                maximum_age_hours=high,
                reasons=("OBSERVATION_INTERVAL_TOO_SHORT",),
            )
        if all(
            MIN_MEANINGFUL_INTERVAL_HOURS <= age
            <= MAX_MEANINGFUL_INTERVAL_HOURS
            for age in ages
        ):
            return _result(
                WINDOW_CANDIDATE,
                candidate=True,
                populations_found=len(latest),
                minimum_age_hours=low,
                maximum_age_hours=high,
                reasons=(
                    "SEPARATE_EXECUTION_PREFLIGHT_AND_APPROVAL_REQUIRED",
                ),
            )
        return _result(
            FAIL_CLOSED,
            populations_found=len(latest),
            minimum_age_hours=low,
            maximum_age_hours=high,
            reasons=("POPULATION_WINDOWS_INCONSISTENT",),
        )
    except Exception:
        return _result(FAIL_CLOSED, reasons=("TEMPORAL_ASSESSMENT_ERROR",))


def main() -> int:
    result = assess_temporal_continuation(as_of=datetime.now(timezone.utc))
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 2 if result.status == FAIL_CLOSED else 0


if __name__ == "__main__":
    raise SystemExit(main())


def main() -> int:
    result = assess_temporal_continuation(
        as_of=datetime.now(timezone.utc)
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {WAIT, LONG_GAP_BLOCKED} else 2


if __name__ == "__main__":
    raise SystemExit(main())
