"""Fixture-only collector response bridge for the approved temporal adapter."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, Sequence

import temporal_approved_active_runner_connection as connection
import temporal_probe_series_integration_adapter as bundle_adapter
from temporal_runbook_policy import FIXED_POPULATIONS


VERSION = "0.1-candidate"
COMPLETE = "ISOLATED_COLLECTOR_BRIDGE_COMPLETE"
BLOCKED = "ISOLATED_COLLECTOR_BRIDGE_BLOCKED"
RECOVERY_REQUIRED = "ISOLATED_COLLECTOR_BRIDGE_RECOVERY_REQUIRED"
MIN_REQUEST_INTERVAL_SECONDS = 1.0
RETRY_COUNT = 0
RESPONSE_FIELDS = frozenset(
    {"request", "success", "result_count", "items", "error_classification"}
)
REQUEST_FIELDS = frozenset({"source_sort", "offset", "hits"})
ITEM_FIELDS = frozenset({"content_id"})
KNOWN_ERRORS = frozenset({"RATE_LIMIT", "HTTP_ERROR", "API_ERROR"})


@dataclass(frozen=True)
class IsolatedCollectorBridgeResult:
    version: str
    status: str
    success: bool
    planned_request_count: int
    attempted_request_count: int
    validated_response_count: int
    assessed_population_count: int
    persisted_population_count: int
    stopped_early: bool
    retry_count: int
    filesystem_access_performed: bool
    active_runner_connected: bool
    live_api_authorized: bool
    scheduler_change_authorized: bool
    production_write_authorized: bool
    deploy_allowed: bool
    publication_allowed: bool
    affiliate_activation_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(
    status: str,
    *,
    attempted: int = 0,
    validated: int = 0,
    assessed: int = 0,
    persisted: int = 0,
    stopped: bool = True,
    accessed: bool = False,
    connected: bool = False,
    success: bool = False,
    reason: str,
) -> IsolatedCollectorBridgeResult:
    return IsolatedCollectorBridgeResult(
        VERSION, status, success, len(FIXED_POPULATIONS), attempted, validated,
        assessed, persisted, stopped, RETRY_COUNT, accessed, connected,
        False, False, False, False, False, False, (reason,),
    )


def _sanitize_response(value: Any, identity: tuple[str, int, int]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != RESPONSE_FIELDS:
        raise ValueError("MALFORMED_RESPONSE")
    request = value["request"]
    if (
        not isinstance(request, Mapping)
        or set(request) != REQUEST_FIELDS
        or tuple(request.get(key) for key in ("source_sort", "offset", "hits"))
        != identity
    ):
        raise ValueError("REQUEST_IDENTITY_MISMATCH")
    if type(value["success"]) is not bool:
        raise ValueError("MALFORMED_RESPONSE")
    if value["success"] is False:
        if value["error_classification"] not in KNOWN_ERRORS:
            raise ValueError("UNKNOWN_ERROR_CLASSIFICATION")
        raise RuntimeError(value["error_classification"])
    if value["error_classification"] is not None:
        raise ValueError("MALFORMED_RESPONSE")
    result_count = value["result_count"]
    items = value["items"]
    if (
        type(result_count) is not int
        or result_count < 0
        or result_count > identity[2]
        or not isinstance(items, list)
        or len(items) != result_count
    ):
        raise ValueError("MALFORMED_RESPONSE")
    sanitized_items: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping) or set(item) != ITEM_FIELDS:
            raise ValueError("MALFORMED_RESPONSE")
        content_id = item["content_id"]
        if not isinstance(content_id, str) or not content_id.strip():
            raise ValueError("MALFORMED_RESPONSE")
        if content_id in seen:
            raise ValueError("DUPLICATE_CONTENT_ID")
        seen.add(content_id)
        sanitized_items.append({"content_id": content_id})
    return {
        "source_sort": identity[0],
        "offset": identity[1],
        "hits": identity[2],
        "result_count": result_count,
        "items": sanitized_items,
    }


class IsolatedCollectorResponseBridge:
    def __init__(
        self,
        fetcher: Callable[[tuple[str, int, int]], Any],
        delay: Callable[[float], None],
        marker: object,
    ):
        if marker is not _TEST_MARKER or not callable(fetcher) or not callable(delay):
            raise ValueError("test factory required")
        self._fetcher = fetcher
        self._delay = delay

    @classmethod
    def for_test(
        cls,
        *,
        fetcher: Callable[[tuple[str, int, int]], Any],
        delay: Callable[[float], None],
    ) -> "IsolatedCollectorResponseBridge":
        return cls(fetcher, delay, _TEST_MARKER)

    def run(
        self,
        *,
        approval: Any,
        series_id: str,
        captured_at: datetime,
        as_of: datetime,
        documents_by_population: Mapping[tuple[str, int, int], Sequence[Any]],
        history_counts: Mapping[tuple[str, int, int], Any],
        store: Any,
        request_interval_seconds: float = MIN_REQUEST_INTERVAL_SECONDS,
    ) -> IsolatedCollectorBridgeResult:
        """Fetch fixture responses sequentially, then validate and connect once."""

        attempted = 0
        payloads: list[dict[str, Any]] = []
        try:
            if (
                type(request_interval_seconds) not in {int, float}
                or request_interval_seconds < MIN_REQUEST_INTERVAL_SECONDS
                or request_interval_seconds > 60.0
            ):
                return _result(BLOCKED, reason="REQUEST_INTERVAL_INVALID")
            for index, identity in enumerate(FIXED_POPULATIONS):
                if index:
                    self._delay(float(request_interval_seconds))
                attempted += 1
                try:
                    payloads.append(_sanitize_response(self._fetcher(identity), identity))
                except RuntimeError as error:
                    code = str(error)
                    return _result(
                        BLOCKED, attempted=attempted, validated=len(payloads),
                        reason=code if code in KNOWN_ERRORS else "FETCH_FAILED",
                    )
            bundle = bundle_adapter.build_validated_series_state_bundle(
                series_id=series_id,
                captured_at=captured_at,
                as_of=as_of,
                payloads=payloads,
            )
            if not bundle.success:
                return _result(
                    BLOCKED, attempted=attempted, validated=len(payloads),
                    reason="ATOMIC_BUNDLE_VALIDATION_FAILED",
                )
            outcome = connection.connect_approved_isolated_active_runner(
                approval=approval,
                bundle=bundle,
                documents_by_population=documents_by_population,
                history_counts=history_counts,
                store=store,
                as_of=as_of,
            )
            if outcome.status == connection.RECOVERY_REQUIRED:
                return _result(
                    RECOVERY_REQUIRED, attempted=attempted, validated=len(payloads),
                    assessed=outcome.assessed_population_count,
                    persisted=outcome.persisted_population_count,
                    accessed=outcome.filesystem_access_performed,
                    reason="DOWNSTREAM_RECOVERY_REQUIRED",
                )
            if outcome.status != connection.CONNECTED or outcome.success is not True:
                return _result(
                    BLOCKED, attempted=attempted, validated=len(payloads),
                    accessed=outcome.filesystem_access_performed,
                    reason="APPROVED_CONNECTION_NOT_COMPLETE",
                )
            return _result(
                COMPLETE, attempted=attempted, validated=len(payloads),
                assessed=outcome.assessed_population_count,
                persisted=outcome.persisted_population_count,
                stopped=False, accessed=outcome.filesystem_access_performed,
                connected=True, success=True,
                reason="FIXTURE_RESPONSES_CONNECTED_ATOMICALLY",
            )
        except Exception:
            return _result(
                BLOCKED, attempted=attempted, validated=len(payloads),
                reason="ISOLATED_COLLECTOR_BRIDGE_ERROR",
            )


_TEST_MARKER = object()

__all__ = [
    "BLOCKED", "COMPLETE", "IsolatedCollectorBridgeResult",
    "IsolatedCollectorResponseBridge", "MIN_REQUEST_INTERVAL_SECONDS",
    "RECOVERY_REQUIRED", "RETRY_COUNT", "VERSION",
]
