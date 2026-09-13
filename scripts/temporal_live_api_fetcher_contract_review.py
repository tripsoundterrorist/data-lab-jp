"""Fail-closed contract review for a future inert temporal API fetcher."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

import revenue_mvp_official_followup_status as followup
import revenue_mvp_temporal_collector_bridge_evidence as bridge_evidence
import temporal_probe_adapter as probe
from temporal_runbook_policy import FIXED_POPULATIONS


VERSION = "0.1"
READY_BLOCKED = "INERT_FETCHER_DESIGN_READY_OFFICIAL_SEMANTICS_BLOCKED"
BLOCKED = "LIVE_FETCHER_CONTRACT_REVIEW_BLOCKED"
NEXT_GATE = "IMPLEMENT_INERT_TEMPORAL_API_FETCHER_CANDIDATE"


@dataclass(frozen=True)
class LiveApiFetcherContractReview:
    version: str
    status: str
    bridge_evidence_verified: bool
    fixed_request_contract_verified: bool
    official_response_pending: bool
    official_sort_semantics_resolved: bool
    inert_implementation_allowed: bool
    live_api_request_authorized: bool
    credentials_access_authorized: bool
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


def review_contract() -> LiveApiFetcherContractReview:
    try:
        evidence = bridge_evidence.assess_bridge_evidence()
        pending = followup.current_status()
        bridge_ready = (
            evidence.status == bridge_evidence.READY
            and evidence.checks_passed == evidence.checks_required == 8
            and evidence.live_api_request_performed is False
            and evidence.credentials_loaded is False
            and evidence.next_gate == bridge_evidence.NEXT_GATE
        )
        request_ready = (
            FIXED_POPULATIONS
            == (("rank", 1, 100), ("rank", 101, 100),
                ("review", 1, 100), ("review", 101, 100))
            and probe.SITE == "FANZA"
            and probe.SERVICE == "digital"
            and probe.FLOOR == "videoa"
            and probe.RETRY_COUNT == 0
            and probe.STOP_ON_RATE_LIMIT is True
        )
        official_pending = (
            pending.status == followup.SUBMITTED_AWAITING_RESPONSE
            and pending.response_received is False
            and pending.official_semantics_resolved is False
            and pending.gate_unlock_allowed is False
            and "DMM_SORT_SEMANTICS" in pending.covered_blockers
        )
        ready = bridge_ready and request_ready and official_pending
        return LiveApiFetcherContractReview(
            VERSION, READY_BLOCKED if ready else BLOCKED,
            bridge_ready, request_ready, official_pending, False,
            ready, False, False, False, False, False, False,
            NEXT_GATE if ready else None,
            (
                "INERT_IMPLEMENTATION_ONLY",
                "OFFICIAL_SORT_SEMANTICS_RESPONSE_REQUIRED_BEFORE_LIVE_USE",
            ) if ready else ("LIVE_FETCHER_CONTRACT_INPUT_INCOMPLETE",),
        )
    except Exception:
        return LiveApiFetcherContractReview(
            VERSION, BLOCKED, False, False, False, False,
            False, False, False, False, False, False, False, None,
            ("LIVE_FETCHER_CONTRACT_REVIEW_ERROR",),
        )


def main() -> int:
    result = review_contract()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY_BLOCKED else 2


if __name__ == "__main__":
    raise SystemExit(main())
