"""Fail-closed review before any temporal active-runner connection approval."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

import revenue_mvp_temporal_active_runner_candidate_evidence as evidence
import temporal_active_runner_connection_design as design


VERSION = "0.1"
READY = "READY_FOR_EXPLICIT_ACTIVE_CONNECTION_APPROVAL"
BLOCKED = "ACTIVE_CONNECTION_REVIEW_BLOCKED"
NEXT_GATE = "REQUEST_ACTIVE_RUNNER_CONNECTION_APPROVAL"


@dataclass(frozen=True)
class ActiveRunnerConnectionReview:
    version: str
    status: str
    design_verified: bool
    isolated_candidate_verified: bool
    checks_passed: int
    checks_required: int
    active_connection_authorized: bool
    api_request_authorized: bool
    state_write_authorized: bool
    scheduler_change_authorized: bool
    production_write_authorized: bool
    deploy_allowed: bool
    next_gate: str | None
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def review_active_runner_connection() -> ActiveRunnerConnectionReview:
    """Review bounded repository evidence without connecting the active runner."""

    try:
        designed = design.assess_design()
        candidate = evidence.assess_candidate_evidence()
        design_verified = (
            designed.version == design.VERSION
            and designed.status == design.DESIGN_READY
            and designed.required_boundaries == design.REQUIRED_BOUNDARIES
            and designed.implementation_authorized is False
            and designed.active_connection_authorized is False
            and designed.api_request_authorized is False
            and designed.state_write_authorized is False
            and designed.scheduler_change_authorized is False
            and designed.deploy_allowed is False
        )
        candidate_verified = (
            candidate.version == evidence.VERSION
            and candidate.status == evidence.EVIDENCE_READY
            and candidate.checks_passed == candidate.checks_required == 8
            and candidate.implementation_evidence_candidate is True
            and candidate.test_filesystem_access_performed is True
            and candidate.active_pipeline_connected is False
            and candidate.api_request_authorized is False
            and candidate.production_write_authorized is False
            and candidate.scheduler_change_authorized is False
            and candidate.deploy_allowed is False
        )
        checks = (design_verified, candidate_verified)
        passed = sum(value is True for value in checks)
        ready = passed == len(checks)
        return ActiveRunnerConnectionReview(
            VERSION, READY if ready else BLOCKED,
            design_verified, candidate_verified, passed, len(checks),
            False, False, False, False, False, False,
            NEXT_GATE if ready else None,
            (
                "ISOLATED_ACTIVE_RUNNER_REVIEW_COMPLETE",
                "EXPLICIT_ACTIVE_CONNECTION_APPROVAL_REQUIRED",
            ) if ready else ("ACTIVE_CONNECTION_EVIDENCE_INCOMPLETE",),
        )
    except Exception:
        return ActiveRunnerConnectionReview(
            VERSION, BLOCKED, False, False, 0, 2,
            False, False, False, False, False, False, None,
            ("ACTIVE_CONNECTION_REVIEW_ERROR",),
        )


def main() -> int:
    result = review_active_runner_connection()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
