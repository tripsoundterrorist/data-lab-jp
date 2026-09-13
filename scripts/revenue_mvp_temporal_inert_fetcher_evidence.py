"""Fail-closed evidence review for the inert temporal API fetcher candidate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import inspect
import json
from typing import Any

import revenue_mvp_official_followup_status as followup
import temporal_inert_api_fetcher_candidate as candidate
import temporal_isolated_collector_response_bridge as bridge
import temporal_live_api_fetcher_contract_review as contract
from temporal_runbook_policy import FIXED_POPULATIONS


VERSION = "0.1"
READY_WAITING = "INERT_FETCHER_VERIFIED_WAITING_FOR_OFFICIAL_RESPONSE"
BLOCKED = "INERT_FETCHER_EVIDENCE_BLOCKED"
NEXT_GATE = "CLASSIFY_OFFICIAL_RESPONSE_BEFORE_LIVE_FETCHER_REVIEW"
CHECKS_REQUIRED = 9


@dataclass(frozen=True)
class InertFetcherEvidence:
    version: str
    status: str
    checks_passed: int
    checks_required: int
    fixed_requests_verified: bool
    response_reduction_verified: bool
    bounded_failures_verified: bool
    official_response_pending: bool
    live_api_request_performed: bool
    credentials_loaded: bool
    state_write_performed: bool
    scheduler_change_authorized: bool
    production_write_authorized: bool
    deploy_allowed: bool
    next_gate: str | None
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _payload(identity: tuple[str, int, int], *, malformed: bool = False):
    item = {"content_id": f"fixture-{identity[0]}-{identity[1]}"}
    if malformed:
        item = {"title": "private-value"}
    return {"result": {"status": "200", "result_count": 1, "items": [item]}}


def assess_inert_fetcher() -> InertFetcherEvidence:
    checks: list[bool] = []
    fixed = reduced = bounded = official_pending = False
    try:
        reviewed = contract.review_contract()
        checks.append(
            reviewed.status == contract.READY_BLOCKED
            and reviewed.inert_implementation_allowed is True
            and reviewed.live_api_request_authorized is False
            and reviewed.credentials_access_authorized is False
        )

        requests = [candidate.prepare_request(identity) for identity in FIXED_POPULATIONS]
        fixed = all(
            request.query["sort"] == identity[0]
            and request.query["offset"] == identity[1]
            and request.query["hits"] == identity[2]
            and request.executable is False
            for request, identity in zip(requests, FIXED_POPULATIONS)
        )
        checks.append(fixed)
        checks.append(all(
            request.live_api_request_authorized is False
            and request.credentials_access_authorized is False
            and request.state_write_authorized is False
            and request.scheduler_change_authorized is False
            and request.production_write_authorized is False
            and request.deploy_allowed is False
            for request in requests
        ))

        identity = FIXED_POPULATIONS[0]
        response = candidate.reduce_response(
            identity, http_status=200, payload=_payload(identity)
        )
        reduced = (
            set(response) == bridge.RESPONSE_FIELDS
            and set(response["request"]) == bridge.REQUEST_FIELDS
            and len(response["items"]) == 1
            and set(response["items"][0]) == bridge.ITEM_FIELDS
        )
        checks.append(reduced)

        failures = (
            candidate.reduce_response(identity, http_status=429, payload={}),
            candidate.classify_transport_failure(identity, "TIMEOUT"),
            candidate.classify_transport_failure(identity, {"private": "value"}),
            candidate.reduce_response(
                identity, http_status=200, payload=_payload(identity, malformed=True)
            ),
        )
        bounded = [value["error_classification"] for value in failures] == [
            "RATE_LIMIT", "HTTP_ERROR", "API_ERROR", "API_ERROR"
        ]
        checks.append(bounded)
        checks.append(all(value["success"] is False for value in failures))

        rendered = json.dumps(
            [request.to_dict() for request in requests] + [response] + list(failures),
            ensure_ascii=True,
        ).casefold()
        checks.append(all(
            value not in rendered
            for value in ("private-value", "credential-value", "exception text")
        ))

        source = inspect.getsource(candidate)
        checks.append(all(
            value not in source
            for value in ("urllib.request", "urlopen", "requests.", "os.environ", "dotenv")
        ))

        pending = followup.current_status()
        official_pending = (
            pending.status == followup.SUBMITTED_AWAITING_RESPONSE
            and pending.response_received is False
            and pending.official_semantics_resolved is False
            and pending.gate_unlock_allowed is False
            and "DMM_SORT_SEMANTICS" in pending.covered_blockers
        )
        checks.append(official_pending)

        passed = sum(value is True for value in checks)
        ready = len(checks) == CHECKS_REQUIRED and passed == CHECKS_REQUIRED
        return InertFetcherEvidence(
            VERSION, READY_WAITING if ready else BLOCKED, passed, CHECKS_REQUIRED,
            fixed, reduced, bounded, official_pending,
            False, False, False, False, False, False,
            NEXT_GATE if ready else None,
            (
                "INERT_FETCHER_BOUNDARY_VERIFIED",
                "OFFICIAL_RESPONSE_REQUIRED_BEFORE_LIVE_REVIEW",
            ) if ready else ("INERT_FETCHER_EVIDENCE_INCOMPLETE",),
        )
    except Exception:
        return InertFetcherEvidence(
            VERSION, BLOCKED, 0, CHECKS_REQUIRED, False, False, False, False,
            False, False, False, False, False, False, None,
            ("INERT_FETCHER_EVIDENCE_ERROR",),
        )


def main() -> int:
    result = assess_inert_fetcher()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY_WAITING else 2


if __name__ == "__main__":
    raise SystemExit(main())
