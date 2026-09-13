"""Bounded executable evidence for the isolated temporal collector bridge."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
from typing import Any

import temporal_approved_active_runner_connection as connection
import temporal_collector_bundle_connection_design as design
import temporal_filesystem_persistence_candidate as filesystem
import temporal_isolated_collector_response_bridge as bridge
from temporal_runbook_policy import FIXED_POPULATIONS


VERSION = "0.1"
READY = "ISOLATED_COLLECTOR_BRIDGE_EVIDENCE_READY"
BLOCKED = "ISOLATED_COLLECTOR_BRIDGE_EVIDENCE_BLOCKED"
NEXT_GATE = "REVIEW_LIVE_TEMPORAL_API_FETCHER_CONTRACT"
CHECKS_REQUIRED = 8
BASE = datetime(2026, 9, 13, tzinfo=timezone.utc)
AS_OF = BASE + timedelta(hours=1)


@dataclass(frozen=True)
class CollectorBridgeEvidence:
    version: str
    status: str
    checks_passed: int
    checks_required: int
    isolated_implementation_verified: bool
    fixture_fetch_count: int
    test_filesystem_access_performed: bool
    live_api_request_performed: bool
    credentials_loaded: bool
    scheduler_change_authorized: bool
    production_write_authorized: bool
    deploy_allowed: bool
    publication_allowed: bool
    affiliate_activation_allowed: bool
    next_gate: str | None
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _response(identity: tuple[str, int, int], *, rate_limited: bool = False):
    return {
        "request": {
            "source_sort": identity[0], "offset": identity[1], "hits": identity[2]
        },
        "success": not rate_limited,
        "result_count": 0 if rate_limited else 1,
        "items": [] if rate_limited else [
            {"content_id": f"fixture-{identity[0]}-{identity[1]}"}
        ],
        "error_classification": "RATE_LIMIT" if rate_limited else None,
    }


def _approval():
    return connection.ActiveRunnerConnectionApproval(
        connection.APPROVAL_VERSION, connection.APPROVAL_SCOPE, True
    )


def _mappings(value: Any):
    return {identity: value for identity in FIXED_POPULATIONS}


def assess_bridge_evidence() -> CollectorBridgeEvidence:
    checks: list[bool] = []
    fetch_count = 0
    accessed = False
    try:
        designed = design.assess_design()
        checks.append(
            designed.status == design.READY
            and designed.implementation_authorized is False
            and designed.api_request_authorized is False
            and designed.scheduler_change_authorized is False
        )

        fetched: list[tuple[str, int, int]] = []

        def fixture_fetcher(identity):
            fetched.append(identity)
            return _response(identity)

        delays: list[float] = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = filesystem.IsolatedTemporalStateStore.for_test(root)
            subject = bridge.IsolatedCollectorResponseBridge.for_test(
                fetcher=fixture_fetcher, delay=delays.append
            )
            result = subject.run(
                approval=_approval(),
                series_id="series-20260913T000000Z-b1c2d3e4",
                captured_at=BASE,
                as_of=AS_OF,
                documents_by_population=_mappings(()),
                history_counts=_mappings(0),
                store=store,
            )
            fetch_count = len(fetched)
            accessed = result.filesystem_access_performed
            files = tuple(root.glob("*.json"))
            checks.append(
                result.status == bridge.COMPLETE
                and result.success is True
                and result.attempted_request_count == 4
                and result.validated_response_count == 4
                and result.assessed_population_count == 4
                and result.persisted_population_count == 4
            )
            checks.append(fetched == list(FIXED_POPULATIONS))
            checks.append(delays == [1.0, 1.0, 1.0])
            checks.append(accessed is True and len(files) == 4)
            checks.append(
                result.live_api_authorized is False
                and result.scheduler_change_authorized is False
                and result.production_write_authorized is False
                and result.deploy_allowed is False
                and result.publication_allowed is False
                and result.affiliate_activation_allowed is False
            )

        limited_calls: list[tuple[str, int, int]] = []

        def limited_fetcher(identity):
            limited_calls.append(identity)
            return _response(identity, rate_limited=len(limited_calls) == 2)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            limited = bridge.IsolatedCollectorResponseBridge.for_test(
                fetcher=limited_fetcher, delay=lambda _seconds: None
            ).run(
                approval=_approval(),
                series_id="series-20260913T000000Z-c1d2e3f4",
                captured_at=BASE,
                as_of=AS_OF,
                documents_by_population=_mappings(()),
                history_counts=_mappings(0),
                store=filesystem.IsolatedTemporalStateStore.for_test(root),
            )
            checks.append(
                limited.status == bridge.BLOCKED
                and limited.reason_codes == ("RATE_LIMIT",)
                and len(limited_calls) == 2
                and not tuple(root.iterdir())
            )

        safe = json.dumps(result.to_dict(), ensure_ascii=True).casefold()
        checks.append(all(
            value not in safe
            for value in ("fixture-rank", "series-", "content_id", "https://")
        ))
        passed = sum(value is True for value in checks)
        ready = len(checks) == CHECKS_REQUIRED and passed == CHECKS_REQUIRED
        return CollectorBridgeEvidence(
            VERSION, READY if ready else BLOCKED, passed, CHECKS_REQUIRED,
            ready, fetch_count, accessed, False, False,
            False, False, False, False, False,
            NEXT_GATE if ready else None,
            (
                "FIXTURE_ONLY_COLLECTOR_BRIDGE_VERIFIED",
                "LIVE_API_FETCHER_REQUIRES_SEPARATE_REVIEW",
            ) if ready else ("COLLECTOR_BRIDGE_EVIDENCE_INCOMPLETE",),
        )
    except Exception:
        return CollectorBridgeEvidence(
            VERSION, BLOCKED, 0, CHECKS_REQUIRED, False, fetch_count, accessed,
            False, False, False, False, False, False, False, None,
            ("COLLECTOR_BRIDGE_EVIDENCE_ERROR",),
        )


def main() -> int:
    result = assess_bridge_evidence()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
