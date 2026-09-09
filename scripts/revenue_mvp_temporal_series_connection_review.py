"""Read-only review Gate for connecting the v0.2 temporal series candidate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import inspect
import json
from typing import Any

import temporal_probe_adapter as active_adapter
import temporal_probe_runner as active_runner
import temporal_probe_series_integration_adapter as integration
import temporal_probe_series_state as series_state
import temporal_probe_state as active_state
import temporal_probe_state_store as active_store


VERSION = "0.1"
CONNECTION_DESIGN_REQUIRED = "CONNECTION_DESIGN_REQUIRED"
FAIL_CLOSED = "FAIL_CLOSED"
REQUIRED_ISOLATED_STEPS = (
    "IMPLEMENT_V02_STATE_STORE_CANDIDATE",
    "IMPLEMENT_V02_RUNNER_CANDIDATE",
    "VERIFY_LEGACY_READ_ONLY_DISCOVERY",
    "VERIFY_SERIES_AWARE_FILENAME_AND_IDENTITY",
    "ADD_DRY_RUN_ONLY_CONNECTION_HARNESS",
)


@dataclass(frozen=True)
class TemporalSeriesConnectionReview:
    version: str
    status: str
    isolated_integration_available: bool
    active_schema_series_aware: bool
    active_runner_series_aware: bool
    active_store_series_aware: bool
    active_adapter_write_path_present: bool
    connection_authorized: bool
    api_request_authorized: bool
    state_write_authorized: bool
    history_migration_authorized: bool
    required_isolated_steps: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["required_isolated_steps"] = list(self.required_isolated_steps)
        value["reason_codes"] = list(self.reason_codes)
        return value


def assess_temporal_series_connection() -> TemporalSeriesConnectionReview:
    """Identify exact incompatibilities without invoking either pipeline."""

    try:
        integration_available = callable(
            integration.run_series_integration_dry_run
        )
        schema_aware = (
            "series_id" in active_state.STATE_FIELDS
            and "series_id" in active_state.POPULATION_IDENTITY_FIELDS
        )
        runner_aware = "series_id" in inspect.signature(
            active_runner.run_temporal_probe
        ).parameters
        store_aware = (
            active_store.serialize_temporal_probe_state
            is series_state.serialize_temporal_probe_series_state
            and "series" in active_store.STATE_FILENAME.pattern
        )
        adapter_source = inspect.getsource(active_adapter.adapt_response)
        write_path_present = "dry_run=False" in adapter_source
        expected_legacy_boundary = (
            integration_available
            and not schema_aware
            and not runner_aware
            and not store_aware
            and write_path_present
        )
        if not expected_legacy_boundary:
            return TemporalSeriesConnectionReview(
                VERSION, FAIL_CLOSED, integration_available, schema_aware,
                runner_aware, store_aware, write_path_present,
                False, False, False, False, REQUIRED_ISOLATED_STEPS,
                ("CONNECTION_BOUNDARY_CHANGED_OR_INCOMPLETE",),
            )
        return TemporalSeriesConnectionReview(
            VERSION, CONNECTION_DESIGN_REQUIRED, True,
            False, False, False, True,
            False, False, False, False, REQUIRED_ISOLATED_STEPS,
            (
                "ACTIVE_CHAIN_USES_LEGACY_STATE_BOUNDARY",
                "DIRECT_CONNECTION_WOULD_ENTER_WRITE_PATH",
                "PARALLEL_V02_CANDIDATES_REQUIRED",
            ),
        )
    except Exception:
        return TemporalSeriesConnectionReview(
            VERSION, FAIL_CLOSED, False, False, False, False, False,
            False, False, False, False, (),
            ("TEMPORAL_SERIES_CONNECTION_REVIEW_ERROR",),
        )


def main() -> int:
    result = assess_temporal_series_connection()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == CONNECTION_DESIGN_REQUIRED else 2


if __name__ == "__main__":
    raise SystemExit(main())
