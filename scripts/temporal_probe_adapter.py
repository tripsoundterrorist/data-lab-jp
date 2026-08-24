"""Fail-closed bridge from minimal probe responses to the temporal runner.

The adapter performs no HTTP or database access.  A future caller supplies a
request function; raw content IDs live only in the validated response and the
short-lived runner input assembled here.

Version 0.1 deliberately keeps already-persisted states after a later request
fails.  It stops immediately and does not attempt an unsafe cross-file rollback.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Any, Callable, Mapping

from temporal_probe_runner import RunnerResult, run_temporal_probe
import temporal_probe_state_store as state_store


SITE = "FANZA"
SERVICE = "digital"
FLOOR = "videoa"
HITS = 100
ALLOWED_POPULATIONS = (
    ("rank", 1),
    ("rank", 101),
    ("review", 1),
    ("review", 101),
)
RETRY_COUNT = 0
STOP_ON_RATE_LIMIT = True
RESPONSE_FIELDS = frozenset(
    {
        "request",
        "success",
        "result_count",
        "total_count",
        "elapsed_ms",
        "items",
        "error_classification",
    }
)
REQUEST_FIELDS = frozenset({"site", "service", "floor", "source_sort", "offset", "hits"})
ITEM_FIELDS = frozenset(
    {
        "content_id",
        "review_average_present",
        "review_count_present",
        "metadata_present",
    }
)
KNOWN_ERROR_CLASSIFICATIONS = frozenset({"RATE_LIMIT", "HTTP_ERROR", "API_ERROR"})
SAFE_RUNNER_REASON = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")


@dataclass(frozen=True)
class ProbeRequest:
    site: str
    service: str
    floor: str
    source_sort: str
    offset: int
    hits: int

    def to_dict(self) -> dict[str, str | int]:
        return {
            "site": self.site,
            "service": self.service,
            "floor": self.floor,
            "source_sort": self.source_sort,
            "offset": self.offset,
            "hits": self.hits,
        }


@dataclass(frozen=True)
class RequestPlan:
    requests: tuple[ProbeRequest, ...]
    request_delay_seconds: float
    retry_count: int = RETRY_COUNT
    stop_on_rate_limit: bool = STOP_ON_RATE_LIMIT


@dataclass(frozen=True)
class SafePopulationResult:
    success: bool
    source_sort: str
    offset: int
    hits: int
    result_count: int | None
    total_count: int | None
    returned_count: int | None
    elapsed_ms: int | None
    review_average_coverage: int | None
    review_count_coverage: int | None
    metadata_coverage: int | None
    duplicate_count: int | None
    runner_success: bool
    state_saved: bool
    comparison_available: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class AdapterExecutionResult:
    success: bool
    dry_run: bool
    planned_request_count: int
    attempted_request_count: int
    completed_request_count: int
    stopped_early: bool
    partial_success_policy: str
    results: tuple[SafePopulationResult, ...]
    reason_codes: tuple[str, ...]


class ResponseValidationError(Exception):
    pass


def build_request_plan(request_delay_seconds: float = 1.0) -> RequestPlan:
    if (
        isinstance(request_delay_seconds, bool)
        or not isinstance(request_delay_seconds, (int, float))
        or request_delay_seconds < 1.0
        or request_delay_seconds > 60.0
    ):
        raise ValueError("invalid request delay")
    return RequestPlan(
        requests=tuple(
            ProbeRequest(SITE, SERVICE, FLOOR, source_sort, offset, HITS)
            for source_sort, offset in ALLOWED_POPULATIONS
        ),
        request_delay_seconds=float(request_delay_seconds),
    )


def _valid_request(request: ProbeRequest) -> bool:
    return (
        request.site == SITE
        and request.service == SERVICE
        and request.floor == FLOOR
        and request.hits == HITS
        and (request.source_sort, request.offset) in ALLOWED_POPULATIONS
    )


def _validate_identity(value: Any, expected: ProbeRequest) -> None:
    if not isinstance(value, Mapping) or set(value) != REQUEST_FIELDS:
        raise ResponseValidationError("MALFORMED_RESPONSE")
    if dict(value) != expected.to_dict():
        raise ResponseValidationError("REQUEST_IDENTITY_MISMATCH")


def _safe_runner_reasons(result: RunnerResult) -> tuple[str, ...]:
    reasons = result.reason_codes
    if not isinstance(reasons, tuple) or any(
        not isinstance(code, str) or SAFE_RUNNER_REASON.fullmatch(code) is None
        for code in reasons
    ):
        return ("RUNNER_FAILURE",)
    return reasons


def _failure(expected: ProbeRequest, code: str, *, elapsed_ms: int | None = None) -> SafePopulationResult:
    return SafePopulationResult(
        False, expected.source_sort, expected.offset, expected.hits,
        None, None, None, elapsed_ms, None, None, None, None,
        False, False, False, (code,),
    )


def adapt_response(
    response: Any,
    expected: ProbeRequest,
    *,
    captured_at: datetime,
    as_of: datetime,
    runner: Callable[..., RunnerResult] = run_temporal_probe,
    output_directory: Path = state_store.DEFAULT_STATE_DIRECTORY,
) -> SafePopulationResult:
    """Validate one minimal response, invoke Runner, and return aggregates only."""

    try:
        if not _valid_request(expected):
            return _failure(expected, "REQUEST_NOT_ALLOWED")
        if not isinstance(response, Mapping) or set(response) != RESPONSE_FIELDS:
            return _failure(expected, "MALFORMED_RESPONSE")
        _validate_identity(response["request"], expected)
        success = response["success"]
        error = response["error_classification"]
        elapsed_ms = response["elapsed_ms"]
        if isinstance(elapsed_ms, bool) or not isinstance(elapsed_ms, int) or elapsed_ms < 0:
            raise ResponseValidationError("MALFORMED_RESPONSE")
        if not isinstance(success, bool):
            raise ResponseValidationError("MALFORMED_RESPONSE")
        if not success:
            if error not in KNOWN_ERROR_CLASSIFICATIONS:
                raise ResponseValidationError("UNKNOWN_ERROR_CLASSIFICATION")
            return _failure(expected, error, elapsed_ms=elapsed_ms)
        if error is not None:
            raise ResponseValidationError("MALFORMED_RESPONSE")

        result_count = response["result_count"]
        total_count = response["total_count"]
        items = response["items"]
        if (
            isinstance(result_count, bool)
            or not isinstance(result_count, int)
            or result_count < 0
            or result_count > expected.hits
            or isinstance(total_count, bool)
            or not isinstance(total_count, int)
            or total_count < result_count
            or not isinstance(items, list)
            or result_count != len(items)
        ):
            raise ResponseValidationError("MALFORMED_RESPONSE")

        content_ids: list[str] = []
        average_count = count_count = metadata_count = 0
        for item in items:
            if not isinstance(item, Mapping) or set(item) != ITEM_FIELDS:
                raise ResponseValidationError("MALFORMED_RESPONSE")
            content_id = item["content_id"]
            flags = (
                item["review_average_present"],
                item["review_count_present"],
                item["metadata_present"],
            )
            if not isinstance(content_id, str) or not content_id.strip() or any(
                not isinstance(flag, bool) for flag in flags
            ):
                raise ResponseValidationError("MALFORMED_RESPONSE")
            content_ids.append(content_id)
            average_count += int(flags[0])
            count_count += int(flags[1])
            metadata_count += int(flags[2])
        duplicate_count = len(content_ids) - len(set(content_ids))
        if duplicate_count:
            raise ResponseValidationError("DUPLICATE_CONTENT_ID")

        runner_input = {
            "captured_at": captured_at,
            "site": expected.site,
            "service": expected.service,
            "floor": expected.floor,
            "source_sort": expected.source_sort,
            "offset": expected.offset,
            "hits": expected.hits,
            "result_count": result_count,
            "items": [{"content_id": value} for value in content_ids],
        }
        runner_result = runner(
            runner_input, as_of=as_of, dry_run=False, output_directory=output_directory
        )
        if not isinstance(runner_result, RunnerResult):
            raise ResponseValidationError("RUNNER_FAILURE")
        reasons = _safe_runner_reasons(runner_result)
        return SafePopulationResult(
            success=runner_result.success,
            source_sort=expected.source_sort,
            offset=expected.offset,
            hits=expected.hits,
            result_count=result_count,
            total_count=total_count,
            returned_count=len(items),
            elapsed_ms=elapsed_ms,
            review_average_coverage=average_count,
            review_count_coverage=count_count,
            metadata_coverage=metadata_count,
            duplicate_count=duplicate_count,
            runner_success=runner_result.success,
            state_saved=runner_result.state_saved,
            comparison_available=runner_result.comparison_available,
            reason_codes=reasons if runner_result.success else ("RUNNER_FAILURE",),
        )
    except ResponseValidationError as error:
        return _failure(expected, str(error))
    except Exception:
        return _failure(expected, "INTERNAL_ADAPTER_ERROR")


def execute_plan(
    *,
    captured_at: datetime,
    as_of: datetime,
    fetch_response: Callable[[ProbeRequest], Any] | None = None,
    runner: Callable[..., RunnerResult] = run_temporal_probe,
    output_directory: Path = state_store.DEFAULT_STATE_DIRECTORY,
    request_delay_seconds: float = 1.0,
    delay: Callable[[float], None] | None = None,
    dry_run: bool = False,
) -> AdapterExecutionResult:
    """Execute the fixed plan sequentially; never retry or roll back successes."""

    try:
        plan = build_request_plan(request_delay_seconds)
        if dry_run:
            return AdapterExecutionResult(
                True, True, len(plan.requests), 0, 0, False,
                "PRESERVE_COMPLETED_STATES_STOP_REMAINING", (), ("DRY_RUN_PLAN_ONLY",),
            )
        if fetch_response is None or delay is None:
            raise ValueError("execution dependency missing")
        results: list[SafePopulationResult] = []
        attempted = 0
        for index, request in enumerate(plan.requests):
            if index:
                delay(plan.request_delay_seconds)
            attempted += 1
            try:
                response = fetch_response(request)
            except Exception:
                result = _failure(request, "REQUEST_CLIENT_FAILURE")
            else:
                result = adapt_response(
                    response,
                    request,
                    captured_at=captured_at,
                    as_of=as_of,
                    runner=runner,
                    output_directory=output_directory,
                )
            results.append(result)
            if not result.success:
                break
        complete = len(results) == len(plan.requests) and all(item.success for item in results)
        return AdapterExecutionResult(
            complete, False, len(plan.requests), attempted,
            sum(item.success for item in results), not complete,
            "PRESERVE_COMPLETED_STATES_STOP_REMAINING", tuple(results),
            () if complete else (results[-1].reason_codes[0],),
        )
    except Exception:
        return AdapterExecutionResult(
            False, dry_run, 0, 0, 0, True,
            "PRESERVE_COMPLETED_STATES_STOP_REMAINING", (),
            ("INTERNAL_ADAPTER_ERROR",),
        )


__all__ = [
    "ALLOWED_POPULATIONS",
    "AdapterExecutionResult",
    "ProbeRequest",
    "RequestPlan",
    "SafePopulationResult",
    "adapt_response",
    "build_request_plan",
    "execute_plan",
]
