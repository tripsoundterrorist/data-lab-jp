"""Pure integration from orchestrator summaries to stability assessments.

The pipeline validates and routes safe aggregate values.  Metric calculation,
thresholds, interval rules, and readiness rules remain owned by the stability
policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath
import re
from typing import Any, Mapping

from temporal_stability_policy import (
    ANOMALOUS_COMPARISON,
    HIGH,
    INSUFFICIENT_HISTORY,
    INVALID_INPUT,
    LOW,
    MODERATE,
    NOT_EVALUATED,
    OBSERVATION_ONLY,
    REVIEW_ELIGIBLE,
    UNKNOWN,
    StabilityAssessment,
    StabilityInput,
    assess_temporal_stability,
)


PIPELINE_VERSION = "0.1"
FIXED_POPULATIONS = (
    ("rank", 1, 100),
    ("rank", 101, 100),
    ("review", 1, 100),
    ("review", 101, 100),
)
TOP_LEVEL_FIELDS = frozenset(
    {
        "overall_status",
        "planned_count",
        "executed_count",
        "succeeded_count",
        "failed_count",
        "skipped_count",
        "stopped_early",
        "stop_reason_code",
        "retry_count",
        "stop_on_error",
        "partial_success_policy",
        "populations",
    }
)
POPULATION_FIELDS = frozenset(
    {
        "source_sort", "offset", "hits", "success", "result_count",
        "total_count", "returned_count", "elapsed_ms",
        "review_average_coverage", "review_count_coverage",
        "metadata_coverage", "duplicate_count", "state_saved",
        "state_filename", "reason", "comparison_available",
        "previous_captured_at", "current_captured_at", "previous_count",
        "current_count", "retained_count", "entered_count", "exited_count",
        "retention_rate", "entry_rate", "exit_rate", "jaccard",
        "turnover_rate",
    }
)
FORBIDDEN_KEYS = frozenset(
    {
        "content_id", "content_ids", "anonymous_item_id",
        "anonymous_item_ids", "product_id", "title", "url", "urls",
        "credentials", "credential", "raw_state", "raw_response",
        "traceback", "exception", "file_path", "absolute_path",
    }
)
SAFE_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
KNOWN_CLASSIFICATIONS = frozenset(
    {INSUFFICIENT_HISTORY, OBSERVATION_ONLY, ANOMALOUS_COMPARISON, INVALID_INPUT}
)
KNOWN_BANDS = frozenset({LOW, MODERATE, HIGH, UNKNOWN})
KNOWN_READINESS = frozenset({NOT_EVALUATED, REVIEW_ELIGIBLE})

ASSESSED = "ASSESSED"
NOT_ASSESSED = "NOT_ASSESSED"
NOT_RUN = "NOT_RUN"

NO_COMPARISONS = "NO_COMPARISONS"
OBSERVATIONS_AVAILABLE = "OBSERVATIONS_AVAILABLE"
PARTIAL_ASSESSMENT = "PARTIAL_ASSESSMENT"
ASSESSMENT_ANOMALY = "ASSESSMENT_ANOMALY"


@dataclass(frozen=True)
class PopulationAssessment:
    source_sort: str
    offset: int
    hits: int
    execution_success: bool | None
    execution_reason: str | None
    assessment_status: str
    comparison_available: bool
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
    classification: str | None
    observation_band: str
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


@dataclass(frozen=True)
class PipelineResult:
    pipeline_version: str
    orchestrator_status: str
    assessment_status: str
    planned_count: int
    assessed_count: int
    not_assessed_count: int
    not_run_count: int
    populations: tuple[PopulationAssessment, ...]
    safe_reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **{
                key: value
                for key, value in self.__dict__.items()
                if key not in {"populations", "safe_reason_codes"}
            },
            "populations": [value.to_dict() for value in self.populations],
            "safe_reason_codes": list(self.safe_reason_codes),
        }


def _forbidden(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str) or key.lower() in FORBIDDEN_KEYS:
                return True
            if _forbidden(nested):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_forbidden(item) for item in value)
    elif isinstance(value, str):
        if "://" in value or re.match(r"[A-Za-z]:[\\/]", value):
            return True
        if value.startswith(("/", "\\\\")):
            return True
    return False


def _safe_code(value: Any, *, nullable: bool = False) -> bool:
    return (nullable and value is None) or (
        isinstance(value, str) and SAFE_CODE.fullmatch(value) is not None
    )


def _not_run(identity: tuple[str, int, int]) -> PopulationAssessment:
    return PopulationAssessment(
        *identity, None, None, NOT_RUN, False, None,
        None, None, None, None, None, None, None, None, None,
        None, UNKNOWN, NOT_EVALUATED, ("POPULATION_NOT_RUN",),
    )


def _not_assessed(value: Mapping[str, Any], reason: str) -> PopulationAssessment:
    return PopulationAssessment(
        value["source_sort"], value["offset"], value["hits"],
        value["success"], value.get("reason"), NOT_ASSESSED, False, None,
        None, None, None, None, None, None, None, None, None,
        None, UNKNOWN, NOT_EVALUATED, (reason,),
    )


def _from_policy(
    execution: Mapping[str, Any], assessment: StabilityAssessment
) -> PopulationAssessment:
    return PopulationAssessment(
        assessment.source_sort,
        assessment.offset,
        assessment.hits,
        True,
        execution["reason"],
        ASSESSED,
        assessment.comparison_available,
        assessment.interval_hours,
        assessment.previous_count,
        assessment.current_count,
        assessment.retained_count,
        assessment.entered_count,
        assessment.exited_count,
        assessment.retention_rate,
        assessment.jaccard,
        assessment.turnover_rate,
        assessment.population_complete,
        assessment.classification,
        assessment.observation_band,
        assessment.production_readiness,
        assessment.safe_reason_codes,
    )


def _policy_output_valid(
    assessment: Any, identity: tuple[str, int, int]
) -> bool:
    return (
        isinstance(assessment, StabilityAssessment)
        and (assessment.source_sort, assessment.offset, assessment.hits) == identity
        and assessment.classification in KNOWN_CLASSIFICATIONS
        and assessment.observation_band in KNOWN_BANDS
        and assessment.production_readiness in KNOWN_READINESS
        and isinstance(assessment.safe_reason_codes, tuple)
        and all(_safe_code(code) for code in assessment.safe_reason_codes)
    )


def _failure(reason: str) -> PipelineResult:
    return PipelineResult(
        PIPELINE_VERSION, "INVALID", ASSESSMENT_ANOMALY,
        0, 0, 0, 0, (), (reason,),
    )


def _validate_top(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) != TOP_LEVEL_FIELDS:
        return False
    integer_fields = (
        "planned_count", "executed_count", "succeeded_count",
        "failed_count", "skipped_count", "retry_count",
    )
    if any(
        not isinstance(value[field], int)
        or isinstance(value[field], bool)
        or value[field] < 0
        for field in integer_fields
    ):
        return False
    if value["planned_count"] not in {0, 4} or value["retry_count"] != 0:
        return False
    if not isinstance(value["stopped_early"], bool) or value["stop_on_error"] is not True:
        return False
    if value["overall_status"] not in {"SUCCESS", "PARTIAL_FAILURE", "FAILURE", "DRY_RUN"}:
        return False
    if value["partial_success_policy"] != "PRESERVE_COMPLETED_STATES_STOP_REMAINING":
        return False
    if not _safe_code(value["stop_reason_code"], nullable=True):
        return False
    if not isinstance(value["populations"], list):
        return False
    return (
        value["executed_count"] + value["skipped_count"] == value["planned_count"]
        and value["succeeded_count"] + value["failed_count"] == value["executed_count"]
    )


def _aggregate_contract(value: Mapping[str, Any]) -> bool:
    aggregate_fields = (
        "result_count", "total_count", "returned_count", "elapsed_ms",
        "review_average_coverage", "review_count_coverage",
        "metadata_coverage", "duplicate_count",
    )
    if any(
        item is not None
        and (not isinstance(item, int) or isinstance(item, bool) or item < 0)
        for item in (value[field] for field in aggregate_fields)
    ):
        return False
    if value["success"] is True:
        required = [value[field] for field in aggregate_fields]
        if any(item is None for item in required) or value["state_saved"] is not True:
            return False
        returned = value["returned_count"]
        return (
            value["result_count"] == returned
            and value["total_count"] >= returned
            and returned <= value["hits"]
            and value["duplicate_count"] == 0
            and all(
                value[field] <= returned
                for field in (
                    "review_average_coverage", "review_count_coverage",
                    "metadata_coverage",
                )
            )
        )
    return value["state_saved"] is False


def _assess_pipeline(
    orchestrator_result: Any,
    history_counts: Mapping[tuple[str, int, int], int],
) -> PipelineResult:
    if _forbidden(orchestrator_result) or not _validate_top(orchestrator_result):
        return _failure("ORCHESTRATOR_RESULT_INVALID")
    if not isinstance(history_counts, Mapping):
        return _failure("HISTORY_COUNTS_INVALID")
    if any(
        key not in FIXED_POPULATIONS
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count < 0
        for key, count in history_counts.items()
    ):
        return _failure("HISTORY_COUNTS_INVALID")

    raw_populations = orchestrator_result["populations"]
    if any(not isinstance(value, Mapping) or set(value) != POPULATION_FIELDS for value in raw_populations):
        return _failure("POPULATION_RESULT_INVALID")
    if any(not _aggregate_contract(value) for value in raw_populations):
        return _failure("POPULATION_AGGREGATE_INVALID")
    identities = [
        (value["source_sort"], value["offset"], value["hits"])
        for value in raw_populations
    ]
    if any(identity not in FIXED_POPULATIONS for identity in identities) or len(set(identities)) != len(identities):
        return _failure("POPULATION_IDENTITY_INVALID")
    if orchestrator_result["overall_status"] == "DRY_RUN":
        if identities != list(FIXED_POPULATIONS) or orchestrator_result["executed_count"] != 0:
            return _failure("DRY_RUN_CONTRACT_INVALID")
    elif identities != list(FIXED_POPULATIONS[: len(identities)]):
        return _failure("POPULATION_ORDER_INVALID")
    elif len(raw_populations) != orchestrator_result["executed_count"]:
        return _failure("EXECUTED_COUNT_MISMATCH")
    if orchestrator_result["overall_status"] != "DRY_RUN" and (
        sum(value["success"] is True for value in raw_populations)
        != orchestrator_result["succeeded_count"]
        or sum(value["success"] is False for value in raw_populations)
        != orchestrator_result["failed_count"]
    ):
        return _failure("EXECUTION_SUMMARY_MISMATCH")

    assessed_by_identity: dict[tuple[str, int, int], PopulationAssessment] = {}
    anomaly = False
    for execution, identity in zip(raw_populations, identities):
        if not isinstance(execution["success"], (bool, type(None))):
            return _failure("POPULATION_SUCCESS_INVALID")
        if not isinstance(execution["state_saved"], bool) or not isinstance(execution["comparison_available"], bool):
            return _failure("POPULATION_FLAGS_INVALID")
        if not _safe_code(execution["reason"], nullable=True):
            return _failure("POPULATION_REASON_INVALID")
        filename = execution["state_filename"]
        if filename is not None and (
            not isinstance(filename, str)
            or PurePath(filename).name != filename
            or _forbidden(filename)
        ):
            return _failure("STATE_FILENAME_INVALID")
        if execution["success"] is None:
            assessed_by_identity[identity] = _not_run(identity)
            continue
        if execution["success"] is False:
            assessed_by_identity[identity] = _not_assessed(
                execution, execution["reason"] or "EXECUTION_FAILED"
            )
            continue
        if identity not in history_counts:
            return _failure("HISTORY_COUNT_REQUIRED")

        comparison_available = execution["comparison_available"]
        stability_input = StabilityInput(
            source_sort=identity[0],
            offset=identity[1],
            hits=identity[2],
            previous_captured_at=(execution["previous_captured_at"] if comparison_available else None),
            current_captured_at=(execution["current_captured_at"] if comparison_available else None),
            previous_count=(execution["previous_count"] if comparison_available else None),
            current_count=(execution["current_count"] if comparison_available else None),
            retained_count=(execution["retained_count"] if comparison_available else None),
            entered_count=(execution["entered_count"] if comparison_available else None),
            exited_count=(execution["exited_count"] if comparison_available else None),
            retention_rate=(execution["retention_rate"] if comparison_available else None),
            entry_rate=(execution["entry_rate"] if comparison_available else None),
            exit_rate=(execution["exit_rate"] if comparison_available else None),
            jaccard=(execution["jaccard"] if comparison_available else None),
            turnover_rate=(execution["turnover_rate"] if comparison_available else None),
            comparison_available=comparison_available,
            history_count=history_counts[identity],
        )
        assessment = assess_temporal_stability(stability_input)
        if not _policy_output_valid(assessment, identity):
            assessed_by_identity[identity] = _not_assessed(execution, "POLICY_OUTPUT_INVALID")
            anomaly = True
            continue
        assessed_by_identity[identity] = _from_policy(execution, assessment)
        if assessment.classification in {ANOMALOUS_COMPARISON, INVALID_INPUT}:
            anomaly = True

    populations = tuple(
        assessed_by_identity.get(identity, _not_run(identity))
        for identity in FIXED_POPULATIONS[: orchestrator_result["planned_count"]]
    )
    assessed_count = sum(value.assessment_status == ASSESSED for value in populations)
    not_assessed_count = sum(value.assessment_status == NOT_ASSESSED for value in populations)
    not_run_count = sum(value.assessment_status == NOT_RUN for value in populations)
    comparisons = sum(value.comparison_available for value in populations if value.assessment_status == ASSESSED)
    if anomaly:
        overall = ASSESSMENT_ANOMALY
    elif not_assessed_count or not_run_count:
        overall = PARTIAL_ASSESSMENT
    elif comparisons:
        overall = OBSERVATIONS_AVAILABLE
    else:
        overall = NO_COMPARISONS
    return PipelineResult(
        PIPELINE_VERSION,
        orchestrator_result["overall_status"],
        overall,
        orchestrator_result["planned_count"],
        assessed_count,
        not_assessed_count,
        not_run_count,
        populations,
        (),
    )


def assess_orchestrator_result(
    orchestrator_result: Any,
    *,
    history_counts: Mapping[tuple[str, int, int], int],
) -> PipelineResult:
    """Validate an orchestrator summary and apply the existing policy."""

    try:
        return _assess_pipeline(orchestrator_result, history_counts)
    except Exception:
        return _failure("INTERNAL_PIPELINE_ERROR")


__all__ = [
    "ASSESSED", "ASSESSMENT_ANOMALY", "FIXED_POPULATIONS", "NOT_ASSESSED",
    "NOT_RUN", "NO_COMPARISONS", "OBSERVATIONS_AVAILABLE",
    "PARTIAL_ASSESSMENT", "PIPELINE_VERSION", "PipelineResult",
    "PopulationAssessment", "assess_orchestrator_result",
]
