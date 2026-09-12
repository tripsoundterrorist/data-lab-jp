"""Bounded executable evidence for the isolated active-runner candidate."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
from typing import Any

import temporal_active_runner_connection_candidate as candidate
import temporal_active_runner_connection_design as design
import temporal_filesystem_persistence_candidate as filesystem
import temporal_probe_series_integration_adapter as adapter
from temporal_runbook_policy import FIXED_POPULATIONS


VERSION = "0.1"
EVIDENCE_READY = "ISOLATED_ACTIVE_RUNNER_EVIDENCE_READY"
BLOCKED = "ISOLATED_ACTIVE_RUNNER_EVIDENCE_BLOCKED"
CHECKS_REQUIRED = 8
BASE = datetime(2026, 9, 12, tzinfo=timezone.utc)
AS_OF = BASE + timedelta(hours=1)


@dataclass(frozen=True)
class ActiveRunnerCandidateEvidence:
    version: str
    status: str
    checks_passed: int
    checks_required: int
    implementation_evidence_candidate: bool
    test_filesystem_access_performed: bool
    active_pipeline_connected: bool
    api_request_authorized: bool
    production_write_authorized: bool
    scheduler_change_authorized: bool
    deploy_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _bundle() -> adapter.ValidatedSeriesStateBundle:
    payloads = [
        {
            "source_sort": source_sort,
            "offset": offset,
            "hits": hits,
            "result_count": 1,
            "items": [{"content_id": f"evidence-{source_sort}-{offset}"}],
        }
        for source_sort, offset, hits in FIXED_POPULATIONS
    ]
    return adapter.build_validated_series_state_bundle(
        series_id="series-20260912T000000Z-e1d2c3b4",
        captured_at=BASE,
        as_of=AS_OF,
        payloads=payloads,
    )


def _mappings(value: Any) -> dict[tuple[str, int, int], Any]:
    return {identity: value for identity in FIXED_POPULATIONS}


def assess_candidate_evidence() -> ActiveRunnerCandidateEvidence:
    checks: list[bool] = []
    accessed = False
    try:
        designed = design.assess_design()
        checks.append(
            designed.status == design.DESIGN_READY
            and designed.implementation_authorized is False
            and designed.active_connection_authorized is False
        )
        bundle = _bundle()
        checks.append(bundle.success is True and bundle.validated_population_count == 4)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = filesystem.IsolatedTemporalStateStore.for_test(root)
            result = candidate.run_isolated_active_runner_candidate(
                bundle=bundle,
                documents_by_population=_mappings(()),
                history_counts=_mappings(0),
                store=store,
                as_of=AS_OF,
            )
            accessed = result.filesystem_access_performed
            files = tuple(root.glob("*.json"))
            checks.append(
                result.status == candidate.COMPLETE
                and result.success is True
                and result.assessed_population_count == 4
                and result.persisted_population_count == 4
            )
            checks.append(accessed is True and len(files) == 4)
            checks.append(all(path.is_file() and path.stat().st_size > 0 for path in files))
            checks.append(
                result.active_runner_connected is False
                and result.legacy_runner_used is False
                and result.api_request_authorized is False
                and result.production_write_authorized is False
                and result.scheduler_change_authorized is False
                and result.deploy_allowed is False
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = filesystem.IsolatedTemporalStateStore.for_test(root)
            rejected = candidate.run_isolated_active_runner_candidate(
                bundle=replace(bundle, success=False),
                documents_by_population=_mappings(()),
                history_counts=_mappings(0),
                store=store,
                as_of=AS_OF,
            )
            checks.append(
                rejected.status == candidate.BLOCKED
                and rejected.filesystem_access_performed is False
                and not tuple(root.iterdir())
            )
        safe = json.dumps(result.to_dict(), ensure_ascii=True).casefold()
        checks.append(all(value not in safe for value in ("evidence-rank", "series-", "content_id")))

        passed = sum(checks)
        ready = len(checks) == CHECKS_REQUIRED and passed == CHECKS_REQUIRED
        return ActiveRunnerCandidateEvidence(
            VERSION,
            EVIDENCE_READY if ready else BLOCKED,
            passed,
            CHECKS_REQUIRED,
            ready,
            accessed,
            False,
            False,
            False,
            False,
            False,
            (
                "TEST_ONLY_ACTIVE_RUNNER_CANDIDATE_VERIFIED",
                "ACTIVE_CONNECTION_REQUIRES_SEPARATE_APPROVAL",
            ) if ready else ("ACTIVE_RUNNER_CANDIDATE_EVIDENCE_INCOMPLETE",),
        )
    except Exception:
        return ActiveRunnerCandidateEvidence(
            VERSION, BLOCKED, 0, CHECKS_REQUIRED, False, accessed,
            False, False, False, False, False,
            ("ACTIVE_RUNNER_CANDIDATE_EVIDENCE_ERROR",),
        )


def main() -> int:
    result = assess_candidate_evidence()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == EVIDENCE_READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
