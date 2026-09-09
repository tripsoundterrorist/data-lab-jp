"""Memory-only bridge from sanitized populations to the v0.2 dry orchestrator."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

import temporal_probe_series_dry_orchestrator as orchestrator
import temporal_probe_series_state as series_state
from temporal_probe_adapter import FLOOR, SERVICE, SITE
from temporal_runbook_policy import FIXED_POPULATIONS


ADAPTER_VERSION = "0.2-candidate"
INTEGRATION_READY = "INTEGRATION_DRY_RUN_COMPLETE"
INTEGRATION_BLOCKED = "INTEGRATION_DRY_RUN_BLOCKED"
PAYLOAD_FIELDS = frozenset({"source_sort", "offset", "hits", "result_count", "items"})
ITEM_FIELDS = frozenset({"content_id"})


@dataclass(frozen=True)
class SeriesIntegrationResult:
    version: str
    status: str
    success: bool
    validated_population_count: int
    active_pipeline_connected: bool
    api_request_authorized: bool
    state_write_authorized: bool
    baseline_activation_authorized: bool
    dry_run: orchestrator.SeriesDryOrchestratorResult | None
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["dry_run"] = self.dry_run.to_dict() if self.dry_run else None
        value["reason_codes"] = list(self.reason_codes)
        return value


class PayloadValidationError(Exception):
    pass


def _blocked(code: str) -> SeriesIntegrationResult:
    return SeriesIntegrationResult(
        ADAPTER_VERSION, INTEGRATION_BLOCKED, False, 0,
        False, False, False, False, None, (code,),
    )


def _content_ids(payload: Any, identity: tuple[str, int, int]) -> tuple[str, ...]:
    if not isinstance(payload, Mapping) or set(payload) != PAYLOAD_FIELDS:
        raise PayloadValidationError("MALFORMED_POPULATION_PAYLOAD")
    source_sort, offset, hits = identity
    if (
        payload["source_sort"] != source_sort
        or payload["offset"] != offset
        or payload["hits"] != hits
    ):
        raise PayloadValidationError("POPULATION_ORDER_OR_IDENTITY_INVALID")
    result_count = payload["result_count"]
    items = payload["items"]
    if (
        isinstance(result_count, bool)
        or not isinstance(result_count, int)
        or result_count < 0
        or result_count > hits
        or not isinstance(items, list)
        or len(items) != result_count
    ):
        raise PayloadValidationError("MALFORMED_POPULATION_PAYLOAD")
    values: list[str] = []
    for item in items:
        if not isinstance(item, Mapping) or set(item) != ITEM_FIELDS:
            raise PayloadValidationError("MALFORMED_POPULATION_PAYLOAD")
        content_id = item["content_id"]
        if not isinstance(content_id, str) or not content_id.strip():
            raise PayloadValidationError("MALFORMED_POPULATION_PAYLOAD")
        values.append(content_id)
    if len(values) != len(set(values)):
        raise PayloadValidationError("DUPLICATE_CONTENT_ID")
    return tuple(values)


def run_series_integration_dry_run(
    *,
    series_id: str,
    captured_at: datetime,
    as_of: datetime,
    payloads: Sequence[Any],
    documents_by_population: Mapping[tuple[str, int, int], Sequence[Any]],
    history_counts: Mapping[tuple[str, int, int], Any],
) -> SeriesIntegrationResult:
    """Validate all four payloads before performing a pure in-memory dry run."""

    try:
        if (
            not isinstance(payloads, Sequence)
            or isinstance(payloads, (str, bytes))
            or len(payloads) != len(FIXED_POPULATIONS)
        ):
            return _blocked("FIXED_POPULATION_PAYLOADS_REQUIRED")
        content_ids = tuple(
            _content_ids(payload, identity)
            for payload, identity in zip(payloads, FIXED_POPULATIONS)
        )
        states = tuple(
            series_state.create_temporal_probe_series_state(
                series_id=series_id,
                captured_at=captured_at,
                site=SITE,
                service=SERVICE,
                floor=FLOOR,
                source_sort=identity[0],
                offset=identity[1],
                hits=identity[2],
                content_ids=values,
            )
            for identity, values in zip(FIXED_POPULATIONS, content_ids)
        )
        result = orchestrator.run_fixed_series_dry_orchestrator(
            current_states=states,
            documents_by_population=documents_by_population,
            history_counts=history_counts,
            as_of=as_of,
        )
        return SeriesIntegrationResult(
            ADAPTER_VERSION,
            INTEGRATION_READY if result.success else INTEGRATION_BLOCKED,
            result.success,
            len(FIXED_POPULATIONS),
            False, False, False, False,
            result,
            ("MEMORY_ONLY_DRY_RUN",) if result.success else ("DOWNSTREAM_DRY_RUN_BLOCKED",),
        )
    except PayloadValidationError as error:
        return _blocked(str(error))
    except Exception:
        return _blocked("SERIES_INTEGRATION_ADAPTER_ERROR")


__all__ = [
    "ADAPTER_VERSION", "INTEGRATION_BLOCKED", "INTEGRATION_READY",
    "SeriesIntegrationResult", "run_series_integration_dry_run",
]
