"""Bounded implementation evidence for the isolated temporal series chain."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
from typing import Any

import revenue_mvp_temporal_series_boundary_gate as active_boundary
import temporal_probe_series_discovery as discovery
import temporal_probe_series_dry_orchestrator as orchestrator
import temporal_probe_series_dry_run as dry_run
import temporal_probe_series_integration_adapter as integration
import temporal_probe_series_state as state_contract


VERSION = "0.2"
EVIDENCE_READY = "IMPLEMENTATION_EVIDENCE_READY"
BLOCKED = "BLOCKED"
BASE = datetime(2026, 9, 9, tzinfo=timezone.utc)
AS_OF = BASE + timedelta(days=4)
SERIES_A = "series-20260909T000000Z-a1b2c3d4"
SERIES_B = "series-20260910T000000Z-b1c2d3e4"


@dataclass(frozen=True)
class TemporalSeriesCandidateEvidence:
    version: str
    status: str
    implementation_evidence_candidate: bool
    isolated_integration_adapter_verified: bool
    active_pipeline_connected: bool
    api_request_authorized: bool
    state_write_authorized: bool
    baseline_activation_authorized: bool
    checks_passed: int
    checks_required: int
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _state(
    identity: tuple[str, int, int],
    captured_at: datetime,
    *,
    series_id: str = SERIES_A,
) -> state_contract.TemporalProbeSeriesState:
    source_sort, offset, hits = identity
    return state_contract.create_temporal_probe_series_state(
        series_id=series_id,
        captured_at=captured_at,
        site="FANZA",
        service="digital",
        floor="videoa",
        source_sort=source_sort,
        offset=offset,
        hits=hits,
        content_ids=("fixture-1", "fixture-2"),
    )


def assess_temporal_series_candidate_evidence(
) -> TemporalSeriesCandidateEvidence:
    """Exercise fixed candidate properties without I/O or activation."""

    try:
        identity = orchestrator.FIXED_POPULATIONS[0]
        previous = _state(identity, BASE)
        current = _state(identity, BASE + timedelta(days=1))
        cross_series = _state(
            identity, BASE + timedelta(days=1), series_id=SERIES_B
        )
        cross_comparison = (
            state_contract.compare_temporal_probe_series_states(
                previous, cross_series, as_of=AS_OF
            )
        )
        legacy_document = state_contract.legacy.serialize_temporal_probe_state(
            previous.legacy_state
        )
        legacy = state_contract.classify_temporal_state_document(
            legacy_document
        )
        cross_discovery = discovery.discover_latest_same_series(
            cross_series,
            (state_contract.serialize_temporal_probe_series_state(previous),),
            as_of=AS_OF,
        )
        baseline = dry_run.run_series_dry_run(
            current, (), as_of=AS_OF, history_count=0
        )
        currents = tuple(
            _state(value, BASE + timedelta(days=1))
            for value in orchestrator.FIXED_POPULATIONS
        )
        documents = {
            value: (
                state_contract.serialize_temporal_probe_series_state(
                    _state(value, BASE)
                ),
            )
            for value in orchestrator.FIXED_POPULATIONS
        }
        histories = {value: 1 for value in orchestrator.FIXED_POPULATIONS}
        fixed = orchestrator.run_fixed_series_dry_orchestrator(
            current_states=currents,
            documents_by_population=documents,
            history_counts=histories,
            as_of=AS_OF,
        )
        payloads = tuple(
            {
                "source_sort": value[0], "offset": value[1], "hits": value[2],
                "result_count": 2,
                "items": [
                    {"content_id": "fixture-1"},
                    {"content_id": "fixture-2"},
                ],
            }
            for value in orchestrator.FIXED_POPULATIONS
        )
        integrated = integration.run_series_integration_dry_run(
            series_id=SERIES_A,
            captured_at=BASE + timedelta(days=1),
            as_of=AS_OF,
            payloads=payloads,
            documents_by_population=documents,
            history_counts=histories,
        )
        active = active_boundary.assess_temporal_series_boundary()
        checks = (
            "series_id" in state_contract.POPULATION_IDENTITY_FIELDS,
            not cross_comparison.comparison_valid
            and cross_comparison.reason_codes == ("CROSS_SERIES_COMPARISON",),
            legacy.status == state_contract.LEGACY_READ_ONLY
            and legacy.readable
            and not legacy.comparison_allowed,
            cross_discovery.status == discovery.EXPLICIT_BASELINE_CANDIDATE
            and cross_discovery.cross_series_excluded_count == 1,
            baseline.status == dry_run.BASELINE_PLANNED
            and baseline.success
            and not baseline.api_request_authorized
            and not baseline.state_write_authorized
            and not baseline.baseline_activation_authorized,
            fixed.status == orchestrator.DRY_RUN_COMPLETE
            and fixed.succeeded_count == 4
            and not fixed.api_request_authorized
            and not fixed.state_write_authorized
            and not fixed.baseline_activation_authorized,
            integrated.status == integration.INTEGRATION_READY
            and integrated.validated_population_count == 4
            and not integrated.active_pipeline_connected
            and not integrated.api_request_authorized
            and not integrated.state_write_authorized
            and not integrated.baseline_activation_authorized,
            active.status == active_boundary.SCHEMA_CHANGE_REQUIRED
            and not active.current_schema_supports_series_boundary
            and not active.current_runner_supports_series_boundary
            and not active.api_request_authorized
            and not active.state_write_authorized,
        )
        passed = sum(check is True for check in checks)
        ready = passed == len(checks)
        return TemporalSeriesCandidateEvidence(
            VERSION,
            EVIDENCE_READY if ready else BLOCKED,
            ready,
            ready,
            False,
            False,
            False,
            False,
            passed,
            len(checks),
            (
                "ISOLATED_SERIES_CANDIDATE_CHAIN_VERIFIED",
                "ISOLATED_INTEGRATION_ADAPTER_VERIFIED",
                "ACTIVE_PIPELINE_CONNECTION_NOT_AUTHORIZED",
            ) if ready else ("SERIES_CANDIDATE_EVIDENCE_INCOMPLETE",),
        )
    except Exception:
        return TemporalSeriesCandidateEvidence(
            VERSION, BLOCKED, False, False, False, False, False, False, 0, 8,
            ("SERIES_CANDIDATE_EVIDENCE_ERROR",),
        )


def main() -> int:
    result = assess_temporal_series_candidate_evidence()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == EVIDENCE_READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
