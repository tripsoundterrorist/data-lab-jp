"""Static design review for a future collector-to-temporal-bundle bridge."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import inspect
import json
from pathlib import Path
from typing import Any

import temporal_approved_active_runner_connection as approved_connection
import temporal_probe_adapter as legacy_adapter
import temporal_probe_series_integration_adapter as bundle_adapter
from temporal_runbook_policy import FIXED_POPULATIONS


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1"
READY = "COLLECTOR_BUNDLE_CONNECTION_DESIGN_READY"
BLOCKED = "COLLECTOR_BUNDLE_CONNECTION_DESIGN_BLOCKED"
NEXT_GATE = "IMPLEMENT_ISOLATED_COLLECTOR_RESPONSE_BRIDGE"
REQUIRED_BOUNDARIES = (
    "FOUR_FIXED_POPULATIONS_ONLY",
    "SANITIZED_RESPONSE_FIELDS_ONLY",
    "VALIDATE_ALL_RESPONSES_BEFORE_STATE_WRITE",
    "NO_LEGACY_DATE_COLLECTOR_REUSE",
    "NO_LEGACY_DRY_RUN_FALSE_ADAPTER_REUSE",
    "ZERO_RETRY_STOP_ON_RATE_LIMIT",
    "MINIMUM_ONE_SECOND_REQUEST_INTERVAL",
    "SERVER_SIDE_CREDENTIAL_ISOLATION",
    "INJECTED_FETCHER_ONLY",
    "SEPARATE_LIVE_API_AND_SCHEDULER_APPROVAL",
)


@dataclass(frozen=True)
class CollectorBundleConnectionDesign:
    version: str
    status: str
    required_boundaries: tuple[str, ...]
    fixed_populations_verified: bool
    bundle_contract_verified: bool
    approved_connection_contract_verified: bool
    legacy_date_collector_reusable: bool
    legacy_response_adapter_reusable: bool
    implementation_authorized: bool
    api_request_authorized: bool
    state_write_authorized: bool
    scheduler_change_authorized: bool
    production_write_authorized: bool
    deploy_allowed: bool
    next_gate: str | None
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["required_boundaries"] = list(self.required_boundaries)
        value["reason_codes"] = list(self.reason_codes)
        return value


def assess_design() -> CollectorBundleConnectionDesign:
    """Inspect contracts and source only; never import or run the live collector."""

    try:
        collector_source = (ROOT / "scripts" / "collect-dmm-items.py").read_text(
            encoding="utf-8"
        )
        fixed = (
            FIXED_POPULATIONS
            == (("rank", 1, 100), ("rank", 101, 100),
                ("review", 1, 100), ("review", 101, 100))
            and legacy_adapter.RETRY_COUNT == 0
            and legacy_adapter.STOP_ON_RATE_LIMIT is True
        )
        bundle_parameters = tuple(inspect.signature(
            bundle_adapter.build_validated_series_state_bundle
        ).parameters)
        bundle_verified = (
            bundle_parameters == ("series_id", "captured_at", "as_of", "payloads")
            and bundle_adapter.PAYLOAD_FIELDS
            == frozenset({"source_sort", "offset", "hits", "result_count", "items"})
            and bundle_adapter.ITEM_FIELDS == frozenset({"content_id"})
        )
        connection_parameters = tuple(inspect.signature(
            approved_connection.connect_approved_isolated_active_runner
        ).parameters)
        connection_verified = connection_parameters == (
            "approval", "bundle", "documents_by_population", "history_counts",
            "store", "as_of",
        )
        date_collector_reusable = not (
            '"sort": "date"' in collector_source
            and "sqlite3.connect(DATABASE_PATH)" in collector_source
            and "urllib.request.urlopen" in collector_source
        )
        legacy_response_adapter_reusable = "dry_run=False" not in inspect.getsource(
            legacy_adapter.adapt_response
        )
        ready = (
            fixed and bundle_verified and connection_verified
            and not date_collector_reusable
            and not legacy_response_adapter_reusable
        )
        return CollectorBundleConnectionDesign(
            VERSION, READY if ready else BLOCKED, REQUIRED_BOUNDARIES,
            fixed, bundle_verified, connection_verified,
            date_collector_reusable, legacy_response_adapter_reusable,
            False, False, False, False, False, False,
            NEXT_GATE if ready else None,
            (
                "ISOLATED_RESPONSE_BRIDGE_REQUIRED",
                "LIVE_API_AND_SCHEDULER_REMAIN_SEPARATE",
            ) if ready else ("COLLECTOR_CONNECTION_BOUNDARY_CHANGED",),
        )
    except Exception:
        return CollectorBundleConnectionDesign(
            VERSION, BLOCKED, REQUIRED_BOUNDARIES,
            False, False, False, False, False,
            False, False, False, False, False, False, None,
            ("COLLECTOR_CONNECTION_DESIGN_ERROR",),
        )


def main() -> int:
    result = assess_design()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
