"""Aggregate memory-only evidence before any active temporal connection."""

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
from typing import Any

import revenue_mvp_temporal_legacy_discovery_evidence as legacy_evidence
import revenue_mvp_temporal_series_connection_review as boundary_review
import revenue_mvp_temporal_series_filename_identity_evidence as identity_evidence
import temporal_probe_series_connection_harness as harness
import temporal_probe_series_runner_candidate as runner
import temporal_probe_series_state as series
import temporal_probe_series_state_store_candidate as store

VERSION = "0.1"
REVIEW_READY = "HUMAN_CONNECTION_REVIEW_READY"
BLOCKED = "BLOCKED"
NEXT_GATE = "REVIEW_DRY_RUN_CONNECTION_CONTRACT"
BASE = datetime(2026, 9, 9, tzinfo=timezone.utc)
AS_OF = BASE + timedelta(days=4)
SERIES_ID = "series-20260909T000000Z-a1b2c3d4"


@dataclass(frozen=True)
class ConnectionReadiness:
    version: str
    status: str
    evidence_complete: bool
    isolated_store_available: bool
    isolated_runner_available: bool
    legacy_read_only_verified: bool
    filename_identity_verified: bool
    four_population_harness_verified: bool
    active_pipeline_connected: bool
    connection_authorized: bool
    api_request_authorized: bool
    state_write_authorized: bool
    baseline_activation_authorized: bool
    checks_passed: int
    checks_required: int
    next_gate: str | None
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _states():
    return tuple(
        series.create_temporal_probe_series_state(
            series_id=SERIES_ID, captured_at=BASE, site="FANZA",
            service="digital", floor="videoa", source_sort=identity[0],
            offset=identity[1], hits=identity[2], content_ids=("fixture-1",),
        )
        for identity in harness.FIXED_POPULATIONS
    )


def assess_connection_readiness() -> ConnectionReadiness:
    """Aggregate candidates while preserving a mandatory human review Gate."""
    try:
        boundary = boundary_review.assess_temporal_series_connection()
        legacy = legacy_evidence.assess_legacy_read_only_discovery()
        identity = identity_evidence.assess_filename_identity()
        documents = {value: () for value in harness.FIXED_POPULATIONS}
        histories = {value: 0 for value in harness.FIXED_POPULATIONS}
        dry = harness.run_dry_connection_harness(
            current_states=_states(), documents_by_population=documents,
            history_counts=histories, as_of=AS_OF,
        )
        store_available = callable(store.plan_series_state_write)
        runner_available = callable(runner.run_temporal_series_candidate)
        legacy_ready = (
            legacy.status == legacy_evidence.EVIDENCE_READY
            and legacy.checks_passed == legacy.checks_required == 7
            and not legacy.legacy_comparison_allowed
            and not legacy.legacy_migration_authorized
        )
        identity_ready = (
            identity.status == identity_evidence.EVIDENCE_READY
            and identity.checks_passed == identity.checks_required == 8
            and not identity.raw_series_id_exposed
        )
        harness_ready = (
            dry.status == harness.HARNESS_COMPLETE
            and dry.succeeded_count == len(harness.FIXED_POPULATIONS)
            and not dry.active_pipeline_connected
            and not dry.filesystem_access_performed
        )
        checks = (
            boundary.status == boundary_review.CONNECTION_DESIGN_REQUIRED,
            boundary.active_adapter_write_path_present,
            not boundary.connection_authorized,
            store_available,
            runner_available,
            legacy_ready,
            identity_ready,
            harness_ready,
            not dry.api_request_authorized,
            not dry.state_write_authorized
            and not dry.baseline_activation_authorized,
        )
        passed = sum(value is True for value in checks)
        ready = passed == len(checks)
        return ConnectionReadiness(
            VERSION, REVIEW_READY if ready else BLOCKED, ready,
            store_available, runner_available, legacy_ready, identity_ready,
            harness_ready, False, False, False, False, False,
            passed, len(checks), NEXT_GATE if ready else None,
            ("ISOLATED_CONNECTION_EVIDENCE_COMPLETE",
             "ACTIVE_CONNECTION_REQUIRES_SEPARATE_REVIEW")
            if ready else ("CONNECTION_READINESS_EVIDENCE_INCOMPLETE",),
        )
    except Exception:
        return ConnectionReadiness(
            VERSION, BLOCKED, False, False, False, False, False, False,
            False, False, False, False, False, 0, 10, None,
            ("CONNECTION_READINESS_EVIDENCE_ERROR",),
        )


def main() -> int:
    result = assess_connection_readiness()
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0 if result.status == REVIEW_READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
