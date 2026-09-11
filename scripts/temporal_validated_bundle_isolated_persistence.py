"""Test-only connection from a validated bundle to isolated persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import temporal_filesystem_persistence_candidate as persistence
import temporal_probe_series_integration_adapter as adapter
import temporal_probe_series_state as state_codec
import temporal_probe_series_state_store_candidate as planner
from temporal_runbook_policy import FIXED_POPULATIONS

VERSION = "0.1-candidate"


@dataclass(frozen=True)
class IsolatedBundlePersistenceResult:
    version: str
    status: str
    success: bool
    persisted_count: int
    filesystem_access_performed: bool
    active_pipeline_connected: bool
    production_write_authorized: bool
    reason_codes: tuple[str, ...]


def _result(status: str, count: int, accessed: bool, *reasons: str,
            success: bool = False) -> IsolatedBundlePersistenceResult:
    return IsolatedBundlePersistenceResult(
        VERSION, status, success, count, accessed, False, False, tuple(reasons)
    )


def persist_validated_bundle_for_test(
    bundle: Any, *, store: Any, as_of: datetime
) -> IsolatedBundlePersistenceResult:
    """Persist exactly one four-state bundle through a test-constructed store."""
    count = 0
    accessed = False
    try:
        if (
            type(bundle) is not adapter.ValidatedSeriesStateBundle
            or bundle.version != adapter.ADAPTER_VERSION
            or bundle.success is not True
            or bundle.validated_population_count != len(FIXED_POPULATIONS)
            or type(bundle.states) is not tuple
            or len(bundle.states) != len(FIXED_POPULATIONS)
            or bundle.active_pipeline_connected is not False
            or bundle.api_request_authorized is not False
            or bundle.state_write_authorized is not False
            or bundle.reason_codes != ("ATOMIC_PAYLOAD_VALIDATION_COMPLETE",)
            or type(store) is not persistence.IsolatedTemporalStateStore
            or type(as_of) is not datetime
        ):
            return _result("PERSISTENCE_BLOCKED", 0, False,
                           "BUNDLE_STORE_OR_TIME_INVALID")
        for value in bundle.states:
            plan = planner.plan_series_state_write(value, as_of=as_of)
            document = (state_codec.serialize_temporal_probe_series_state(value) + "\n").encode("utf-8")
            outcome = store.persist(plan, document)
            accessed = accessed or outcome.filesystem_access_performed
            if outcome.status not in {"PERSISTED_AND_VERIFIED", "IDENTICAL_REPLAY_NOOP"}:
                return _result("RECOVERY_REQUIRED" if outcome.status == "RECOVERY_REQUIRED"
                               else "PERSISTENCE_BLOCKED", count, accessed,
                               "DOWNSTREAM_PERSISTENCE_NOT_COMPLETE")
            if outcome.status == "PERSISTED_AND_VERIFIED":
                count += 1
        return _result("ISOLATED_BUNDLE_PERSISTED", count, accessed,
                       "TEST_ONLY_BUNDLE_WRITE_VERIFIED", success=True)
    except Exception:
        return _result("RECOVERY_REQUIRED" if accessed else "PERSISTENCE_BLOCKED",
                       count, accessed, "ISOLATED_BUNDLE_RESULT_UNCERTAIN")


__all__ = ["IsolatedBundlePersistenceResult", "VERSION",
           "persist_validated_bundle_for_test"]
