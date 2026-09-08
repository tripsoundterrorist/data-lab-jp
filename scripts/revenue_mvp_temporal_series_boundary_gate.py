"""Read-only compatibility Gate for a post-gap temporal series boundary."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import inspect
import json
from typing import Any

import temporal_probe_runner
import temporal_probe_state


VERSION = "0.1"
SCHEMA_CHANGE_REQUIRED = "SCHEMA_CHANGE_REQUIRED"
FAIL_CLOSED = "FAIL_CLOSED"
SERIES_FIELD = "series_id"
REQUIRED_CHANGES = (
    "ADD_SERIES_ID_TO_STATE_SCHEMA",
    "INCLUDE_SERIES_ID_IN_COMPARISON_IDENTITY",
    "PRESERVE_LEGACY_STATE_READABILITY",
    "BLOCK_CROSS_SERIES_COMPARISON",
    "REQUIRE_EXPLICIT_NEW_SERIES_START",
)


@dataclass(frozen=True)
class TemporalSeriesBoundaryGate:
    version: str
    status: str
    current_schema_supports_series_boundary: bool
    current_runner_supports_series_boundary: bool
    api_request_authorized: bool
    state_write_authorized: bool
    history_reset_authorized: bool
    required_changes: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["required_changes"] = list(self.required_changes)
        value["reason_codes"] = list(self.reason_codes)
        return value


def assess_temporal_series_boundary() -> TemporalSeriesBoundaryGate:
    """Report the missing boundary without changing schema, state, or history."""

    try:
        schema_support = (
            SERIES_FIELD in temporal_probe_state.STATE_FIELDS
            and SERIES_FIELD in temporal_probe_state.POPULATION_IDENTITY_FIELDS
        )
        runner_parameters = inspect.signature(
            temporal_probe_runner.run_temporal_probe
        ).parameters
        runner_support = SERIES_FIELD in runner_parameters
        if schema_support or runner_support:
            return TemporalSeriesBoundaryGate(
                VERSION, FAIL_CLOSED, schema_support, runner_support,
                False, False, False, REQUIRED_CHANGES,
                ("PARTIAL_SERIES_BOUNDARY_IMPLEMENTATION_DETECTED",),
            )
        return TemporalSeriesBoundaryGate(
            VERSION,
            SCHEMA_CHANGE_REQUIRED,
            False,
            False,
            False,
            False,
            False,
            REQUIRED_CHANGES,
            (
                "CURRENT_STATE_IDENTITY_HAS_NO_SERIES_BOUNDARY",
                "LONG_GAP_REBASELINE_NOT_IMPLEMENTED",
            ),
        )
    except Exception:
        return TemporalSeriesBoundaryGate(
            VERSION, FAIL_CLOSED, False, False, False, False, False, (),
            ("TEMPORAL_SERIES_BOUNDARY_GATE_ERROR",),
        )


def main() -> int:
    result = assess_temporal_series_boundary()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == SCHEMA_CHANGE_REQUIRED else 2


if __name__ == "__main__":
    raise SystemExit(main())
