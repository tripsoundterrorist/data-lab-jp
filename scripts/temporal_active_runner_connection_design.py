"""Pure design Gate for a future series-aware active runner boundary."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import inspect
import json
from typing import Any

import temporal_probe_adapter as legacy_adapter
import temporal_probe_runner as legacy_runner
import temporal_probe_series_integration_adapter as series_adapter
import temporal_probe_series_runner_candidate as series_runner
import temporal_validated_bundle_isolated_persistence as isolated_persistence


VERSION = "0.1"
DESIGN_READY = "DESIGN_READY_FOR_IMPLEMENTATION_REVIEW"
BLOCKED = "DESIGN_BLOCKED"
REQUIRED_BOUNDARIES = (
    "VALIDATED_FOUR_POPULATION_BUNDLE_INPUT",
    "EXPLICIT_SERIES_IDENTITY",
    "NO_LEGACY_RUNNER_FALLBACK",
    "NO_NETWORK_OR_SCHEDULER_CAPABILITY",
    "INJECTED_TEST_ONLY_PERSISTENCE",
    "ATOMIC_STOP_BEFORE_FIRST_WRITE_ON_INVALID_BUNDLE",
    "BOUNDED_SAFE_RESULT",
    "SEPARATE_IMPLEMENTATION_APPROVAL",
)


@dataclass(frozen=True)
class ActiveRunnerConnectionDesign:
    version: str
    status: str
    design_authorized: bool
    legacy_runner_series_aware: bool
    legacy_adapter_enters_write_path: bool
    validated_bundle_available: bool
    isolated_runner_available: bool
    test_only_persistence_available: bool
    required_boundaries: tuple[str, ...]
    implementation_authorized: bool
    active_connection_authorized: bool
    api_request_authorized: bool
    state_write_authorized: bool
    scheduler_change_authorized: bool
    deploy_allowed: bool
    next_gate: str
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["required_boundaries"] = list(self.required_boundaries)
        value["reason_codes"] = list(self.reason_codes)
        return value


def assess_design() -> ActiveRunnerConnectionDesign:
    """Inspect exact callable boundaries; never invoke either runner."""
    try:
        legacy_series_aware = "series_id" in inspect.signature(
            legacy_runner.run_temporal_probe
        ).parameters
        legacy_write_path = "dry_run=False" in inspect.getsource(
            legacy_adapter.adapt_response
        )
        bundle_available = callable(
            series_adapter.build_validated_series_state_bundle
        )
        runner_available = callable(series_runner.run_temporal_series_candidate)
        persistence_available = callable(
            isolated_persistence.persist_validated_bundle_for_test
        )
        expected = (
            not legacy_series_aware
            and legacy_write_path
            and bundle_available
            and runner_available
            and persistence_available
        )
        if not expected:
            raise ValueError("connection boundary changed")
        return ActiveRunnerConnectionDesign(
            VERSION, DESIGN_READY, True, False, True, True, True, True,
            REQUIRED_BOUNDARIES,
            False, False, False, False, False, False,
            "REVIEW_ACTIVE_RUNNER_CONNECTION_IMPLEMENTATION",
            (
                "LEGACY_WRITE_PATH_MUST_NOT_BE_REUSED",
                "SERIES_AWARE_BOUNDARY_DESIGN_COMPLETE",
                "IMPLEMENTATION_REQUIRES_SEPARATE_APPROVAL",
            ),
        )
    except Exception:
        return ActiveRunnerConnectionDesign(
            VERSION, BLOCKED, False, False, False, False, False, False,
            REQUIRED_BOUNDARIES,
            False, False, False, False, False, False,
            "REASSESS_CONNECTION_BOUNDARY",
            ("ACTIVE_RUNNER_CONNECTION_DESIGN_INPUT_CHANGED",),
        )


def main() -> int:
    result = assess_design()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == DESIGN_READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
