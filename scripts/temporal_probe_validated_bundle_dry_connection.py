"""Memory-only connection from one validated state bundle to the dry harness."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

import temporal_probe_series_connection_harness as harness
import temporal_probe_series_integration_adapter as adapter
from temporal_runbook_policy import FIXED_POPULATIONS


CONNECTION_VERSION = "0.1-candidate"
CONNECTION_COMPLETE = "VALIDATED_BUNDLE_DRY_CONNECTION_COMPLETE"
CONNECTION_BLOCKED = "VALIDATED_BUNDLE_DRY_CONNECTION_BLOCKED"


@dataclass(frozen=True)
class ValidatedBundleDryConnectionResult:
    version: str
    status: str
    success: bool
    validated_population_count: int
    active_pipeline_connected: bool
    filesystem_access_performed: bool
    api_request_authorized: bool
    state_write_authorized: bool
    baseline_activation_authorized: bool
    dry_harness: harness.SeriesConnectionHarnessResult | None
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["dry_harness"] = (
            self.dry_harness.to_dict() if self.dry_harness else None
        )
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(code: str) -> ValidatedBundleDryConnectionResult:
    return ValidatedBundleDryConnectionResult(
        CONNECTION_VERSION, CONNECTION_BLOCKED, False, 0,
        False, False, False, False, False, None, (code,),
    )


def _validated_bundle_envelope(value: Any) -> bool:
    """Check the public bundle envelope without revalidating payloads or states."""
    try:
        return (
            type(value) is adapter.ValidatedSeriesStateBundle
            and set(vars(value)) == {
                "version", "success", "validated_population_count", "states",
                "active_pipeline_connected", "api_request_authorized",
                "state_write_authorized", "reason_codes",
            }
            and value.version == adapter.ADAPTER_VERSION
            and value.success is True
            and value.validated_population_count == len(FIXED_POPULATIONS)
            and type(value.states) is tuple
            and len(value.states) == len(FIXED_POPULATIONS)
            and value.active_pipeline_connected is False
            and value.api_request_authorized is False
            and value.state_write_authorized is False
            and value.reason_codes == ("ATOMIC_PAYLOAD_VALIDATION_COMPLETE",)
        )
    except Exception:
        return False


def connect_validated_bundle_to_dry_harness(
    *, bundle: Any,
    documents_by_population: Mapping[tuple[str, int, int], Sequence[Any]],
    history_counts: Mapping[tuple[str, int, int], Any],
    as_of: datetime,
) -> ValidatedBundleDryConnectionResult:
    """Pass one validated bundle to the existing harness, entirely in memory."""
    try:
        if not _validated_bundle_envelope(bundle):
            return _blocked("VALIDATED_STATE_BUNDLE_INVALID")
        result = harness.run_dry_connection_harness(
            current_states=bundle.states,
            documents_by_population=documents_by_population,
            history_counts=history_counts,
            as_of=as_of,
        )
        if (
            type(result) is not harness.SeriesConnectionHarnessResult
            or result.version != harness.HARNESS_VERSION
            or result.active_pipeline_connected is not False
            or result.filesystem_access_performed is not False
            or result.api_request_authorized is not False
            or result.state_write_authorized is not False
            or result.baseline_activation_authorized is not False
        ):
            return _blocked("DRY_HARNESS_RESULT_INVALID")
        if result.status != harness.HARNESS_COMPLETE or result.success is not True:
            return _blocked("DRY_HARNESS_BLOCKED")
        return ValidatedBundleDryConnectionResult(
            CONNECTION_VERSION, CONNECTION_COMPLETE, True,
            bundle.validated_population_count,
            False, False, False, False, False, result,
            ("VALIDATED_BUNDLE_CONNECTED_TO_DRY_HARNESS",),
        )
    except Exception:
        return _blocked("VALIDATED_BUNDLE_DRY_CONNECTION_ERROR")


__all__ = [
    "CONNECTION_BLOCKED", "CONNECTION_COMPLETE", "CONNECTION_VERSION",
    "ValidatedBundleDryConnectionResult",
    "connect_validated_bundle_to_dry_harness",
]
