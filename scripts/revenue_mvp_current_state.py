"""Current bounded Revenue MVP state from reviewed, repository-held evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import affiliate_d1_production_state
import affiliate_route_deployment_review
import affiliate_runtime_deployment_preflight


ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = ROOT / "runtime" / "evidence" / "revenue-mvp-unordered-edge-verification-receipt-20260922.json"
ARTIFACT_PATH = ROOT / "items" / "index.html"
VERSION = "0.1"
LIVE_AFFILIATE_CLOSED = "REVENUE_SURFACE_LIVE_AFFILIATE_GATE_CLOSED"
FAIL_CLOSED = "CURRENT_REVENUE_STATE_FAIL_CLOSED"
EXPECTED_SHA256 = "862a2c275d0134856ecc9b095f9fe689903337c3c56c90e138dbb4a1e8a4022d"
EXPECTED_COUNT = 100
EXPECTED_ROUTE = "/items/"


@dataclass(frozen=True)
class CurrentRevenueState:
    version: str
    status: str
    revenue_mvp_priority: str
    limited_surface_live: bool
    live_scope: str
    live_route: str | None
    live_item_count: int | None
    edge_artifact_verified: bool
    affiliate_runtime_candidate_ready: bool
    affiliate_d1_lookup_ready: bool
    affiliate_d1_enabled_row_count: int | None
    cta_allowed: bool
    affiliate_integration_allowed: bool
    production_write_allowed: bool
    paid_plan_change_allowed: bool
    next_action: str
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _failed(reason: str) -> CurrentRevenueState:
    return CurrentRevenueState(
        VERSION, FAIL_CLOSED, "P0", False, "UNVERIFIED", None, None, False,
        False, False, None, False, False, False, False,
        "RECONCILE_CURRENT_REVENUE_EVIDENCE", (reason,),
    )


def _canonical_sha256(value: bytes) -> str:
    """Match deployed LF bytes across Git checkouts with different EOL policy."""
    text = value.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def assess(receipt: Any, artifact_bytes: bytes, preflight: Any, route: Any, d1: Any) -> CurrentRevenueState:
    """Validate the live receipt and keep the separate affiliate Gate closed."""
    try:
        receipt_valid = (
            type(receipt) is dict
            and receipt.get("version") == VERSION
            and receipt.get("scope") == "UNORDERED_REDUCED_SURFACE"
            and receipt.get("state") == "EDGE_VERIFIED_LIVE"
            and receipt.get("target_route") == EXPECTED_ROUTE
            and receipt.get("http_status") == 200
            and receipt.get("artifact_sha256") == EXPECTED_SHA256
            and receipt.get("article_count") == EXPECTED_COUNT
            and receipt.get("cloudflare_beacon_present") is False
            and receipt.get("items_javascript_present") is False
            and receipt.get("affiliate_reference_present") is False
            and receipt.get("global_publication_gate") == "unchanged"
            and receipt.get("cta_allowed") is False
            and receipt.get("affiliate_eligibility_allowed") is False
            and receipt.get("d1_write_allowed") is False
            and receipt.get("scope_expansion_allowed") is False
            and "no-transform" in receipt.get("cache_control", "")
            and _canonical_sha256(artifact_bytes) == EXPECTED_SHA256
        )
        affiliate_valid = (
            preflight.deployment_candidate is True
            and preflight.production_deployment_allowed is False
            and route.deployment_review_candidate is True
            and route.affiliate_activation_allowed is False
            and route.production_deployment_allowed is False
            and d1.lookup_ready is True
            and d1.all_rows_disabled is True
            and d1.all_rows_pending is True
            and d1.runtime_eligibility_empty is True
            and d1.cloudflare_write_allowed is False
            and d1.deployment_allowed is False
            and d1.paid_plan_change_allowed is False
        )
        if not receipt_valid:
            return _failed("EDGE_VERIFICATION_RECEIPT_INVALID_OR_STALE")
        if not affiliate_valid:
            return _failed("AFFILIATE_GATE_EVIDENCE_INVALID_OR_OPEN")
        return CurrentRevenueState(
            VERSION, LIVE_AFFILIATE_CLOSED, "P0", True,
            "UNORDERED_REDUCED_SURFACE", EXPECTED_ROUTE, EXPECTED_COUNT, True,
            True, True, 0, False, False, False, False,
            "REVIEW_SEPARATE_AFFILIATE_CTA_GATE",
            (
                "EDGE_ARTIFACT_EXACT_MATCH_VERIFIED",
                "LIMITED_SURFACE_IS_LIVE",
                "AFFILIATE_RUNTIME_REMAINS_INERT",
                "CTA_REQUIRES_SEPARATE_APPROVAL",
                "GLOBAL_PUBLICATION_GATE_UNCHANGED",
            ),
        )
    except Exception:
        return _failed("CURRENT_REVENUE_STATE_EVALUATION_ERROR")


def current_state() -> CurrentRevenueState:
    try:
        receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
        artifact = ARTIFACT_PATH.read_bytes()
    except Exception:
        return _failed("CURRENT_REVENUE_EVIDENCE_UNREADABLE")
    return assess(
        receipt,
        artifact,
        affiliate_runtime_deployment_preflight.assess_preflight(
            affiliate_runtime_deployment_preflight.current_input()
        ),
        affiliate_route_deployment_review.assess(
            affiliate_route_deployment_review.current_evidence()
        ),
        affiliate_d1_production_state.assess(
            affiliate_d1_production_state.current_evidence()
        ),
    )


def main() -> int:
    result = current_state()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == LIVE_AFFILIATE_CLOSED else 2


if __name__ == "__main__":
    raise SystemExit(main())
