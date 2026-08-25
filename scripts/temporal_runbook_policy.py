"""Pure policy contract for Day 3+ temporal probe runbooks.

This module performs no API, filesystem, state, database, or publication
operation.  It only validates the fixed execution contract and describes the
history/readiness transition delegated to Temporal Stability Policy v0.1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from temporal_probe_adapter import FLOOR, HITS, SERVICE, SITE
from temporal_probe_orchestrator import PARTIAL_SUCCESS_POLICY, RETRY_COUNT
from temporal_probe_retention import HOT_RETENTION_DAYS, KEEP_HOT
from temporal_stability_policy import (
    MAX_MEANINGFUL_INTERVAL_HOURS,
    MIN_COMPARISONS_FOR_STABILITY_REVIEW,
    MIN_MEANINGFUL_INTERVAL_HOURS,
    NOT_EVALUATED,
    OBSERVATION_ONLY,
    REVIEW_ELIGIBLE,
)


RUNBOOK_VERSION = "0.1"
FIXED_POPULATIONS = (
    ("rank", 1, 100),
    ("rank", 101, 100),
    ("review", 1, 100),
    ("review", 101, 100),
)
EXECUTION_CHAIN = (
    "ORCHESTRATOR",
    "ADAPTER",
    "RUNNER",
    "STATE_STORE",
    "COMPARISON",
    "STABILITY_POLICY",
    "ASSESSMENT_PIPELINE",
)
MIN_REQUEST_INTERVAL_SECONDS = 1.0
STOP_ON_ERROR = True
NO_ROLLBACK = True
PUBLICATION_UNLOCK_ALLOWED = False
LIFECYCLE_UNLOCK_ALLOWED = False
SEMANTICS_UNLOCK_ALLOWED = False


@dataclass(frozen=True)
class RunbookCheck:
    valid: bool
    history_count: int | None
    classification: str
    production_readiness: str
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "runbook_version": RUNBOOK_VERSION,
            "valid": self.valid,
            "history_count": self.history_count,
            "classification": self.classification,
            "production_readiness": self.production_readiness,
            "reason_codes": list(self.reason_codes),
        }


def validate_run_plan(
    populations: Any,
    *,
    request_interval_seconds: Any = MIN_REQUEST_INTERVAL_SECONDS,
    retry_count: Any = RETRY_COUNT,
    stop_on_error: Any = STOP_ON_ERROR,
) -> tuple[bool, tuple[str, ...]]:
    """Validate the exact four-population, sequential execution contract."""

    reasons: list[str] = []
    if populations != FIXED_POPULATIONS:
        reasons.append("FIXED_POPULATION_PLAN_MISMATCH")
    if (
        isinstance(request_interval_seconds, bool)
        or not isinstance(request_interval_seconds, (int, float))
        or request_interval_seconds < MIN_REQUEST_INTERVAL_SECONDS
    ):
        reasons.append("REQUEST_INTERVAL_INVALID")
    if retry_count != 0 or isinstance(retry_count, bool):
        reasons.append("RETRY_POLICY_INVALID")
    if stop_on_error is not True:
        reasons.append("STOP_ON_ERROR_REQUIRED")
    return not reasons, tuple(reasons)


def assess_history_transition(
    *, previous_history_count: Any, successful_comparisons: Any, interval_hours: Any
) -> RunbookCheck:
    """Fail closed while describing a successful day's history transition."""

    if (
        not isinstance(previous_history_count, int)
        or isinstance(previous_history_count, bool)
        or previous_history_count < 0
        or not isinstance(successful_comparisons, int)
        or isinstance(successful_comparisons, bool)
        or successful_comparisons not in range(5)
        or isinstance(interval_hours, bool)
        or not isinstance(interval_hours, (int, float))
    ):
        return RunbookCheck(False, None, "INVALID", NOT_EVALUATED, ("UNKNOWN_STATE",))
    if interval_hours < MIN_MEANINGFUL_INTERVAL_HOURS:
        return RunbookCheck(False, previous_history_count, "INVALID", NOT_EVALUATED, ("INTERVAL_TOO_SHORT",))
    if interval_hours > MAX_MEANINGFUL_INTERVAL_HOURS:
        return RunbookCheck(False, previous_history_count, "INVALID", NOT_EVALUATED, ("INTERVAL_TOO_LONG",))
    if successful_comparisons != len(FIXED_POPULATIONS):
        return RunbookCheck(
            False,
            previous_history_count,
            "PARTIAL_FAILURE",
            NOT_EVALUATED,
            (PARTIAL_SUCCESS_POLICY, "NO_ROLLBACK", "MANUAL_FOLLOW_UP_REQUIRED"),
        )
    history_count = previous_history_count + 1
    readiness = (
        REVIEW_ELIGIBLE
        if history_count >= MIN_COMPARISONS_FOR_STABILITY_REVIEW
        else NOT_EVALUATED
    )
    return RunbookCheck(
        True,
        history_count,
        OBSERVATION_ONLY,
        readiness,
        ("QUERY_POPULATION_COMPOSITION_OBSERVATION", "MANUAL_REVIEW_REQUIRED"),
    )


__all__ = [
    "EXECUTION_CHAIN", "FIXED_POPULATIONS", "LIFECYCLE_UNLOCK_ALLOWED",
    "MIN_REQUEST_INTERVAL_SECONDS", "NO_ROLLBACK", "PUBLICATION_UNLOCK_ALLOWED",
    "RUNBOOK_VERSION", "SEMANTICS_UNLOCK_ALLOWED", "STOP_ON_ERROR",
    "RunbookCheck", "assess_history_transition", "validate_run_plan",
]
