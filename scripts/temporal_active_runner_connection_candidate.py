"""Isolated candidate joining validated dry assessment to test-only persistence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

import temporal_probe_validated_bundle_dry_connection as dry_connection
import temporal_validated_bundle_isolated_persistence as persistence


VERSION = "0.1-candidate"
COMPLETE = "ISOLATED_ACTIVE_RUNNER_CANDIDATE_COMPLETE"
BLOCKED = "ISOLATED_ACTIVE_RUNNER_CANDIDATE_BLOCKED"
RECOVERY_REQUIRED = "ISOLATED_ACTIVE_RUNNER_CANDIDATE_RECOVERY_REQUIRED"


@dataclass(frozen=True)
class ActiveRunnerConnectionCandidateResult:
    version: str
    status: str
    success: bool
    assessed_population_count: int
    persisted_population_count: int
    filesystem_access_performed: bool
    active_runner_connected: bool
    legacy_runner_used: bool
    api_request_authorized: bool
    production_write_authorized: bool
    scheduler_change_authorized: bool
    deploy_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(
    status: str,
    *,
    success: bool = False,
    assessed: int = 0,
    persisted: int = 0,
    accessed: bool = False,
    reason: str,
) -> ActiveRunnerConnectionCandidateResult:
    return ActiveRunnerConnectionCandidateResult(
        VERSION, status, success, assessed, persisted, accessed,
        False, False, False, False, False, False, (reason,),
    )


def run_isolated_active_runner_candidate(
    *,
    bundle: Any,
    documents_by_population: Mapping[tuple[str, int, int], Sequence[Any]],
    history_counts: Mapping[tuple[str, int, int], Any],
    store: Any,
    as_of: datetime,
) -> ActiveRunnerConnectionCandidateResult:
    """Assess all four states, then persist only through the injected test store."""
    try:
        assessed = dry_connection.connect_validated_bundle_to_dry_harness(
            bundle=bundle,
            documents_by_population=documents_by_population,
            history_counts=history_counts,
            as_of=as_of,
        )
        if (
            type(assessed) is not dry_connection.ValidatedBundleDryConnectionResult
            or assessed.status != dry_connection.CONNECTION_COMPLETE
            or assessed.success is not True
            or assessed.validated_population_count != 4
            or assessed.filesystem_access_performed is not False
            or assessed.active_pipeline_connected is not False
            or assessed.api_request_authorized is not False
            or assessed.state_write_authorized is not False
            or assessed.baseline_activation_authorized is not False
        ):
            return _result(BLOCKED, reason="DRY_ASSESSMENT_NOT_COMPLETE")

        persisted = persistence.persist_validated_bundle_for_test(
            bundle, store=store, as_of=as_of
        )
        if type(persisted) is not persistence.IsolatedBundlePersistenceResult:
            return _result(BLOCKED, assessed=4, reason="PERSISTENCE_RESULT_INVALID")
        if persisted.status == "RECOVERY_REQUIRED":
            return _result(
                RECOVERY_REQUIRED,
                assessed=4,
                persisted=persisted.persisted_count,
                accessed=persisted.filesystem_access_performed,
                reason="ISOLATED_PERSISTENCE_RECOVERY_REQUIRED",
            )
        if persisted.status != "ISOLATED_BUNDLE_PERSISTED" or persisted.success is not True:
            return _result(
                BLOCKED,
                assessed=4,
                persisted=persisted.persisted_count,
                accessed=persisted.filesystem_access_performed,
                reason="ISOLATED_PERSISTENCE_NOT_COMPLETE",
            )
        return _result(
            COMPLETE,
            success=True,
            assessed=4,
            persisted=persisted.persisted_count,
            accessed=persisted.filesystem_access_performed,
            reason="TEST_ONLY_ASSESSMENT_AND_PERSISTENCE_COMPLETE",
        )
    except Exception:
        return _result(BLOCKED, reason="ISOLATED_ACTIVE_RUNNER_CANDIDATE_ERROR")


__all__ = [
    "ActiveRunnerConnectionCandidateResult", "BLOCKED", "COMPLETE",
    "RECOVERY_REQUIRED", "VERSION", "run_isolated_active_runner_candidate",
]
