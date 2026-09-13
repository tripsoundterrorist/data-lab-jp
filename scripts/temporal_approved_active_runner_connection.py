"""Approval-gated connection to the isolated temporal active-runner boundary."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

import revenue_mvp_temporal_active_runner_connection_review as review
import temporal_active_runner_connection_candidate as candidate
import temporal_filesystem_persistence_candidate as filesystem


VERSION = "0.1-candidate"
APPROVAL_VERSION = "0.1"
APPROVAL_SCOPE = "ISOLATED_TEMPORAL_ACTIVE_RUNNER_CONNECTION"
CONNECTED = "APPROVED_ISOLATED_ACTIVE_RUNNER_CONNECTED"
BLOCKED = "ACTIVE_RUNNER_CONNECTION_BLOCKED"
RECOVERY_REQUIRED = "ACTIVE_RUNNER_CONNECTION_RECOVERY_REQUIRED"


@dataclass(frozen=True)
class ActiveRunnerConnectionApproval:
    version: str
    scope: str
    granted: bool


@dataclass(frozen=True)
class ApprovedActiveRunnerConnectionResult:
    version: str
    status: str
    success: bool
    approval_verified: bool
    review_verified: bool
    assessed_population_count: int
    persisted_population_count: int
    filesystem_access_performed: bool
    active_runner_connected: bool
    api_request_authorized: bool
    scheduler_change_authorized: bool
    production_write_authorized: bool
    deploy_allowed: bool
    publication_allowed: bool
    affiliate_activation_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(
    status: str,
    *,
    approval_verified: bool = False,
    review_verified: bool = False,
    assessed: int = 0,
    persisted: int = 0,
    accessed: bool = False,
    connected: bool = False,
    success: bool = False,
    reason: str,
) -> ApprovedActiveRunnerConnectionResult:
    return ApprovedActiveRunnerConnectionResult(
        VERSION, status, success, approval_verified, review_verified,
        assessed, persisted, accessed, connected,
        False, False, False, False, False, False, (reason,),
    )


def connect_approved_isolated_active_runner(
    *,
    approval: Any,
    bundle: Any,
    documents_by_population: Mapping[tuple[str, int, int], Sequence[Any]],
    history_counts: Mapping[tuple[str, int, int], Any],
    store: Any,
    as_of: datetime,
) -> ApprovedActiveRunnerConnectionResult:
    """Connect only to a test-factory store after exact review and approval."""

    try:
        approval_verified = (
            type(approval) is ActiveRunnerConnectionApproval
            and approval.version == APPROVAL_VERSION
            and approval.scope == APPROVAL_SCOPE
            and approval.granted is True
        )
        if not approval_verified:
            return _result(BLOCKED, reason="EXPLICIT_CONNECTION_APPROVAL_REQUIRED")
        reviewed = review.review_active_runner_connection()
        review_verified = (
            reviewed.status == review.READY
            and reviewed.checks_passed == reviewed.checks_required == 2
            and reviewed.next_gate == review.NEXT_GATE
            and reviewed.active_connection_authorized is False
            and reviewed.api_request_authorized is False
            and reviewed.state_write_authorized is False
            and reviewed.scheduler_change_authorized is False
            and reviewed.production_write_authorized is False
            and reviewed.deploy_allowed is False
        )
        if not review_verified or type(store) is not filesystem.IsolatedTemporalStateStore:
            return _result(
                BLOCKED, approval_verified=True,
                reason="REVIEW_OR_ISOLATED_STORE_INVALID",
            )
        outcome = candidate.run_isolated_active_runner_candidate(
            bundle=bundle,
            documents_by_population=documents_by_population,
            history_counts=history_counts,
            store=store,
            as_of=as_of,
        )
        if type(outcome) is not candidate.ActiveRunnerConnectionCandidateResult:
            return _result(
                BLOCKED, approval_verified=True, review_verified=True,
                reason="ACTIVE_RUNNER_RESULT_INVALID",
            )
        if outcome.status == candidate.RECOVERY_REQUIRED:
            return _result(
                RECOVERY_REQUIRED,
                approval_verified=True,
                review_verified=True,
                assessed=outcome.assessed_population_count,
                persisted=outcome.persisted_population_count,
                accessed=outcome.filesystem_access_performed,
                reason="ISOLATED_STATE_RECOVERY_REQUIRED",
            )
        if outcome.status != candidate.COMPLETE or outcome.success is not True:
            return _result(
                BLOCKED,
                approval_verified=True,
                review_verified=True,
                assessed=outcome.assessed_population_count,
                persisted=outcome.persisted_population_count,
                accessed=outcome.filesystem_access_performed,
                reason="ACTIVE_RUNNER_CANDIDATE_NOT_COMPLETE",
            )
        return _result(
            CONNECTED,
            approval_verified=True,
            review_verified=True,
            assessed=outcome.assessed_population_count,
            persisted=outcome.persisted_population_count,
            accessed=outcome.filesystem_access_performed,
            connected=True,
            success=True,
            reason="APPROVED_TEST_ONLY_CONNECTION_COMPLETE",
        )
    except Exception:
        return _result(BLOCKED, reason="ACTIVE_RUNNER_CONNECTION_ERROR")


__all__ = [
    "APPROVAL_SCOPE", "APPROVAL_VERSION", "BLOCKED", "CONNECTED",
    "RECOVERY_REQUIRED", "VERSION", "ActiveRunnerConnectionApproval",
    "ApprovedActiveRunnerConnectionResult",
    "connect_approved_isolated_active_runner",
]
