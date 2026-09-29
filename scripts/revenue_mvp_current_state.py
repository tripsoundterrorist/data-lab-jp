"""Current bounded Revenue MVP state from reviewed, repository-held evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import affiliate_d1_production_state
import affiliate_route_deployment_review
import affiliate_runtime_deployment_preflight


ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = ROOT / "runtime" / "evidence" / "revenue-mvp-unordered-edge-verification-receipt-20260922.json"
ARTIFACT_PATH = ROOT / "items" / "index.html"
VERSION = "0.1"
LIVE_AFFILIATE_CLOSED = "REVENUE_SURFACE_LIVE_AFFILIATE_GATE_CLOSED"
APPROVED_CANARY_PENDING_EDGE = "REVENUE_SURFACE_APPROVED_ONE_CTA_PENDING_EDGE_VERIFICATION"
PRODUCT_CARD_CANARY_PENDING_EDGE = "REVENUE_SURFACE_PRODUCT_CARD_CANARY_PENDING_EDGE_VERIFICATION"
PRODUCT_CARD_LIVE_REVALIDATION_PENDING = "REVENUE_SURFACE_PRODUCT_CARD_LIVE_REVALIDATION_PENDING_FIRST_RUN"
PRODUCT_CARD_LIVE_REVALIDATION_PAUSED = "REVENUE_SURFACE_PRODUCT_CARD_LIVE_REVALIDATION_PAUSED_TRANSPORT_INCOMPATIBLE"
PRODUCT_CARD_LIVE_LOCAL_REVALIDATION_CANARY = "REVENUE_SURFACE_PRODUCT_CARD_LIVE_LOCAL_REVALIDATION_CANARY_VERIFIED"
PRODUCT_CARD_LIVE_LOCAL_SCHEDULER_ACTIVE = "REVENUE_SURFACE_PRODUCT_CARD_LIVE_LOCAL_SCHEDULER_ACTIVE"
FAIL_CLOSED = "CURRENT_REVENUE_STATE_FAIL_CLOSED"
EXPECTED_SHA256 = "862a2c275d0134856ecc9b095f9fe689903337c3c56c90e138dbb4a1e8a4022d"
APPROVED_CANARY_SHA256 = "62ad8f93cc91769b5c92854bc4ff2ccb6bb4e939d8791a8b36245d4c93878374"
APPROVED_CANARY_CANONICAL_SHA256 = "bb65f1a2e8b437de4d1f26e224733c9341aa0d85d46752e12d0c857108d54c11"
CANARY_APPROVAL_PATH = ROOT / "docs" / "evidence" / "revenue-mvp-one-cta-final-user-approval-20260929.json"
PRODUCT_CARD_SHA256 = "c7d569dc732b73e4085c9d860f1a54c73c201b974d37dda7ae15d9c5193dddf1"
DISCOVERY_PRODUCT_CARD_SHA256 = "293f10a921359f3f29091ece45c16e9214ce9164ad53a44c3ce35d38aff76a86"
LATEST_PRODUCT_CARD_SHA256 = "5eece329debeb14e517c20aaf6c7e2ded40488c2ff16f57dbec34afb54a2c2b4"
PRODUCT_CARD_APPROVAL_PATH = ROOT / "docs" / "evidence" / "revenue-mvp-product-card-canary-user-approval-20260929.json"
DISCOVERY_PRODUCT_CARD_APPROVAL_PATH = ROOT / "docs" / "evidence" / "revenue-mvp-product-discovery-user-approval-20260930.json"
LATEST_PRODUCT_CARD_APPROVAL_PATH = ROOT / "docs" / "evidence" / "revenue-mvp-latest-product-user-approval-20260930.json"
PRODUCT_CARD_LIVE_EVIDENCE_PATH = ROOT / "docs" / "evidence" / "revenue-mvp-product-discovery-live-verification-20260930.json"
LATEST_PRODUCT_CARD_LIVE_EVIDENCE_PATH = ROOT / "docs" / "evidence" / "revenue-mvp-latest-product-live-verification-20260930.json"
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


def assess(
    receipt: Any, artifact_bytes: bytes, preflight: Any, route: Any, d1: Any,
    product_card_live_evidence: Any = None,
) -> CurrentRevenueState:
    """Validate the live receipt and keep the separate affiliate Gate closed."""
    try:
        raw_artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
        artifact_sha256 = _canonical_sha256(artifact_bytes)
        product_card_hashes = {
            PRODUCT_CARD_SHA256,
            DISCOVERY_PRODUCT_CARD_SHA256,
            LATEST_PRODUCT_CARD_SHA256,
        }
        if raw_artifact_sha256 in product_card_hashes or artifact_sha256 in product_card_hashes:
            latest_candidate = (
                raw_artifact_sha256 == LATEST_PRODUCT_CARD_SHA256
                or artifact_sha256 == LATEST_PRODUCT_CARD_SHA256
            )
            discovery_candidate = (
                latest_candidate
                or raw_artifact_sha256 == DISCOVERY_PRODUCT_CARD_SHA256
                or artifact_sha256 == DISCOVERY_PRODUCT_CARD_SHA256
            )
            expected_product_card_sha256 = (
                LATEST_PRODUCT_CARD_SHA256 if latest_candidate
                else DISCOVERY_PRODUCT_CARD_SHA256 if discovery_candidate
                else PRODUCT_CARD_SHA256
            )
            approval_path = (
                LATEST_PRODUCT_CARD_APPROVAL_PATH if latest_candidate
                else DISCOVERY_PRODUCT_CARD_APPROVAL_PATH if discovery_candidate
                else PRODUCT_CARD_APPROVAL_PATH
            )
            approval = json.loads(approval_path.read_text(encoding="utf-8"))
            text = artifact_bytes.decode("utf-8")
            scope = approval.get("approved_scope", {})
            image_urls = re.findall(r'<img class="card-image" src="([^"]+)"', text)
            product_card_valid = (
                approval.get("decision") == "APPROVED_FOR_PRODUCTION"
                and scope.get("candidate_sha256") == expected_product_card_sha256
                and scope.get("public_route") == EXPECTED_ROUTE
                and scope.get("item_count") == EXPECTED_COUNT
                and scope.get("image_count") == EXPECTED_COUNT
                and scope.get("maximum_cta_count") == 100
                and text.count('class="item"') == EXPECTED_COUNT
                and len(image_urls) == EXPECTED_COUNT
                and all(url.startswith("https://pics.dmm.co.jp/") for url in image_urls)
                and text.count('class="affiliate-cta-block"') == 100
                and len(re.findall(r'href="/go/itm_[0-9a-f]{24}"', text)) == 100
                and text.count("【PR】") == 100
                and text.count('rel="noopener noreferrer sponsored"') == 100
                and 'name="robots" content="noindex,nofollow"' in text
                and "affiliateURL" not in text
                and (
                    not latest_candidate
                    or (
                        scope.get("source_sha256") == DISCOVERY_PRODUCT_CARD_SHA256
                        and scope.get("reviewed_windows_source_sha256") == "4e5df75fd909f14896958a0ae51929592ce6f2b3931bc6c47b4a0fff52002cf2"
                        and scope.get("reviewed_windows_candidate_sha256") == LATEST_PRODUCT_CARD_SHA256
                        and scope.get("retained_count") == 88
                        and scope.get("added_count") == 12
                        and scope.get("removed_count") == 12
                        and scope.get("candidate_runtime_redirect_matches") == EXPECTED_COUNT
                        and scope.get("discovery_controls_preserved") is True
                        and scope.get("robots_noindex_preserved") is True
                        and scope.get("proximate_pr_disclosure_required") is True
                        and text.count('<script src="discovery.js" defer></script>') == 1
                        and text.count('id="item-search"') == 1
                        and text.count('id="price-filter"') == 1
                        and text.count('id="item-sort"') == 1
                    )
                )
                and (
                    not discovery_candidate or latest_candidate
                    or (
                        scope.get("source_sha256") == PRODUCT_CARD_SHA256
                        and scope.get("reviewed_windows_source_sha256") == "497495a8148e34d752bd0c237d9ea58d114d538f0faeb7bc94652d7b90a65498"
                        and scope.get("reviewed_windows_candidate_sha256") == "4e5df75fd909f14896958a0ae51929592ce6f2b3931bc6c47b4a0fff52002cf2"
                        and scope.get("card_bytes_preserved") is True
                        and scope.get("go_routes_preserved") is True
                        and text.count('<script src="discovery.js" defer></script>') == 1
                        and text.count('id="item-search"') == 1
                        and text.count('id="price-filter"') == 1
                        and text.count('id="item-sort"') == 1
                    )
                )
            )
            if not product_card_valid:
                return _failed("PRODUCT_CARD_CANARY_ARTIFACT_INVALID")
            live = product_card_live_evidence
            production = live.get("production", {}) if type(live) is dict else {}
            private_d1 = live.get("private_d1", {}) if type(live) is dict else {}
            deployment = live.get("deployment", {}) if type(live) is dict else {}
            first_run = deployment.get("first_lifecycle_run", {}) if type(deployment) is dict else {}
            local_canary = deployment.get("local_revalidation_canary", {}) if type(deployment) is dict else {}
            production_verified = (
                type(live) is dict
                and live.get("version") == VERSION
                and live.get("status") == "VERIFIED_LIVE"
                and production.get("route") == EXPECTED_ROUTE
                and production.get("http_status") == 200
                and production.get("artifact_sha256") == expected_product_card_sha256
                and production.get("item_count") == EXPECTED_COUNT
                and production.get("official_image_count") == EXPECTED_COUNT
                and production.get("cta_count") == EXPECTED_COUNT
                and production.get("proximate_pr_disclosure_count") == EXPECTED_COUNT
                and production.get("representative_redirects_tested") == 3
                and production.get("representative_redirects_passed") == 3
                and production.get("invalid_public_id_status") == 404
                and production.get("invalid_public_id_location_absent") is True
                and production.get("private_affiliate_url_exposed") is False
                and re.fullmatch(r"[0-9a-f]{40}", deployment.get("main_commit", "")) is not None
                and re.fullmatch(r"[0-9a-f-]{36}", deployment.get("worker_version_id", "")) is not None
                and deployment.get("lifecycle_cron") is None
                and live.get("global_publication_gate") == "unchanged"
                and live.get("paid_plan_change") is False
            )
            latest_live_verified = (
                latest_candidate
                and production_verified
                and deployment.get("main_commit") == "6a05bf24f3a90d8133ffd6041348462a608a79b1"
                and deployment.get("revalidation_status") == "LOCAL_SCHEDULER_ACTIVE"
                and private_d1.get("enabled_count") == 112
                and private_d1.get("runtime_target_count") == 112
                and private_d1.get("candidate_lookup_matches") == EXPECTED_COUNT
                and private_d1.get("candidate_eligible_matches") == EXPECTED_COUNT
                and private_d1.get("candidate_redirect_matches") == EXPECTED_COUNT
                and private_d1.get("candidate_runtime_redirect_matches") == EXPECTED_COUNT
                and private_d1.get("scoped_revalidation_selected") == 12
                and private_d1.get("scoped_revalidation_valid") == 12
                and private_d1.get("scoped_revalidation_disabled") == 0
            )
            prior_live_verified = (
                not latest_candidate
                and production_verified
                and private_d1.get("enabled_count") == EXPECTED_COUNT
                and private_d1.get("runtime_target_count") == EXPECTED_COUNT
                and deployment.get("first_lifecycle_run_verified") is True
                and deployment.get("revalidation_status") == "LOCAL_SCHEDULER_ACTIVE_PENDING_FIRST_SCHEDULED_RUN"
                and first_run.get("checked_count") == 5
                and first_run.get("valid_count") == 0
                and first_run.get("disabled_count") == 5
                and first_run.get("reason_code") == "PROVIDER_UPSTREAM_UNAVAILABLE"
                and first_run.get("worker_cron_disabled") is True
                and first_run.get("local_official_api_reverified_count") == 5
                and first_run.get("restored_count") == 5
                and first_run.get("enabled_count_after_recovery") == EXPECTED_COUNT
                and local_canary.get("checked_at") == "2026-09-29T15:03:06Z"
                and local_canary.get("selected_count") == 5
                and local_canary.get("valid_count") == 5
                and local_canary.get("disabled_count") == 0
                and local_canary.get("database_write_performed") is True
                and local_canary.get("temporary_sql_deleted") is True
                and local_canary.get("enabled_count_after_canary") == EXPECTED_COUNT
                and local_canary.get("production_smoke_checked_url_count") == 14
                and local_canary.get("production_smoke_failed_url_count") == 0
                and local_canary.get("scheduler_registered") is True
                and local_canary.get("scheduler_time_jst") == "20:00"
                and local_canary.get("scheduler_batch_size") == 5
                and local_canary.get("scheduler_manual_smoke_last_task_result") == 0
                and local_canary.get("scheduler_manual_smoke_valid_count") == 5
                and local_canary.get("scheduler_manual_smoke_disabled_count") == 0
                and local_canary.get("residual_worker_cron_explicitly_removed") is True
            )
            live_verified = latest_live_verified or prior_live_verified
            if live_verified:
                live_reason_codes = (
                    (
                        "PRODUCTION_PRODUCT_CARD_ARTIFACT_EXACT_MATCH_VERIFIED",
                        "ONE_HUNDRED_OFFICIAL_IMAGES_LIVE",
                        "ONE_HUNDRED_PROXIMATE_PR_DISCLOSED_CTAS_LIVE",
                        "CURRENT_SURFACE_D1_RUNTIME_TARGETS_EXACTLY_ONE_HUNDRED",
                        "TWELVE_NEW_ROUTES_SCOPED_REVALIDATION_PASSED",
                        "INVALID_PUBLIC_ID_FAIL_CLOSED_VERIFIED",
                        "LOCAL_REVALIDATION_SCHEDULER_ACTIVE_AT_20_00_JST",
                        "GLOBAL_PUBLICATION_GATE_UNCHANGED",
                    )
                    if latest_candidate
                    else (
                        "PRODUCTION_PRODUCT_CARD_ARTIFACT_EXACT_MATCH_VERIFIED",
                        "ONE_HUNDRED_OFFICIAL_IMAGES_LIVE",
                        "ONE_HUNDRED_PROXIMATE_PR_DISCLOSED_CTAS_LIVE",
                        "CURRENT_SURFACE_D1_RUNTIME_TARGETS_EXACTLY_ONE_HUNDRED",
                        "INVALID_PUBLIC_ID_FAIL_CLOSED_VERIFIED",
                        "WORKER_REVALIDATION_TRANSPORT_INCOMPATIBLE",
                        "WORKER_CRON_DISABLED_AFTER_BOUNDED_FAILURE",
                        "FIVE_ROWS_LOCALLY_REVERIFIED_AND_RESTORED",
                        "LOCAL_REVALIDATION_CANARY_FIVE_OF_FIVE_VALID",
                        "LOCAL_REVALIDATION_SCHEDULER_ACTIVE_AT_20_00_JST",
                        "LOCAL_REVALIDATION_TASK_MANUAL_SMOKE_PASSED",
                        "RESIDUAL_WORKER_CRON_EXPLICITLY_REMOVED",
                        "GLOBAL_PUBLICATION_GATE_UNCHANGED",
                    )
                )
                return CurrentRevenueState(
                    VERSION, PRODUCT_CARD_LIVE_LOCAL_SCHEDULER_ACTIVE, "P0", True,
                    "UNORDERED_REDUCED_SURFACE_PRODUCT_CARD_LIVE", EXPECTED_ROUTE,
                    EXPECTED_COUNT, True, True, True,
                    private_d1.get("enabled_count"), True, True,
                    False, False, "VERIFY_FIRST_AUTOMATIC_LOCAL_REVALIDATION_RUN",
                    live_reason_codes,
                )
            return CurrentRevenueState(
                VERSION, PRODUCT_CARD_CANARY_PENDING_EDGE, "P0", True,
                "UNORDERED_REDUCED_SURFACE_PRODUCT_CARD_CANARY", EXPECTED_ROUTE,
                EXPECTED_COUNT, False, True, True, 100, True, True, False,
                False, "VERIFY_PRODUCT_CARD_CANARY_AT_EDGE",
                (
                    "EXACT_APPROVED_PRODUCT_CARD_ARTIFACT_PRESENT",
                    "ONE_HUNDRED_OFFICIAL_IMAGES_PRESENT",
                    "ONE_HUNDRED_PROXIMATE_PR_DISCLOSED_CTAS_PRESENT",
                    "OPAQUE_SAME_ORIGIN_GO_ROUTE_ONLY",
                    "EDGE_VERIFICATION_REQUIRED_AFTER_DEPLOYMENT",
                    "GLOBAL_PUBLICATION_GATE_UNCHANGED",
                ),
            )
        if (
            raw_artifact_sha256 == APPROVED_CANARY_SHA256
            or artifact_sha256 == APPROVED_CANARY_CANONICAL_SHA256
        ):
            approval = json.loads(CANARY_APPROVAL_PATH.read_text(encoding="utf-8"))
            text = artifact_bytes.decode("utf-8")
            scope = approval.get("approved_scope", {})
            canary_valid = (
                approval.get("decision") == "APPROVED_FOR_PRODUCTION"
                and scope.get("candidate_sha256") == APPROVED_CANARY_SHA256
                and scope.get("public_route") == EXPECTED_ROUTE
                and scope.get("item_count") == EXPECTED_COUNT
                and scope.get("maximum_cta_count") == 1
                and scope.get("proximate_pr_disclosure_required") is True
                and text.count('class="item"') == EXPECTED_COUNT
                and text.count('class="affiliate-cta-block"') == 1
                and len(re.findall(r'href="/go/itm_[0-9a-f]{24}"', text)) == 1
                and text.count("【PR】") == 1
                and 'rel="noopener noreferrer sponsored"' in text
                and 'name="robots" content="noindex,nofollow"' in text
                and "affiliateURL" not in text
            )
            if not canary_valid:
                return _failed("APPROVED_CANARY_ARTIFACT_INVALID")
            return CurrentRevenueState(
                VERSION, APPROVED_CANARY_PENDING_EDGE, "P0", True,
                "UNORDERED_REDUCED_SURFACE_ONE_CTA_CANARY", EXPECTED_ROUTE,
                EXPECTED_COUNT, False, True, True, 1, True, True, False,
                False, "VERIFY_ONE_CTA_CANARY_AT_EDGE",
                (
                    "EXACT_APPROVED_CANARY_ARTIFACT_PRESENT",
                    "ONE_PROXIMATE_PR_DISCLOSED_CTA_PRESENT",
                    "OPAQUE_SAME_ORIGIN_GO_ROUTE_ONLY",
                    "EDGE_VERIFICATION_REQUIRED_AFTER_DEPLOYMENT",
                    "GLOBAL_PUBLICATION_GATE_UNCHANGED",
                ),
            )
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
            and artifact_sha256 == EXPECTED_SHA256
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
        artifact_hashes = {
            hashlib.sha256(artifact).hexdigest(),
            _canonical_sha256(artifact),
        }
        live_evidence_path = (
            LATEST_PRODUCT_CARD_LIVE_EVIDENCE_PATH
            if LATEST_PRODUCT_CARD_SHA256 in artifact_hashes
            else PRODUCT_CARD_LIVE_EVIDENCE_PATH
        )
        product_card_live_evidence = json.loads(live_evidence_path.read_text(encoding="utf-8"))
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
        product_card_live_evidence,
    )


def main() -> int:
    result = current_state()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in (
        LIVE_AFFILIATE_CLOSED, APPROVED_CANARY_PENDING_EDGE,
        PRODUCT_CARD_CANARY_PENDING_EDGE, PRODUCT_CARD_LIVE_REVALIDATION_PENDING,
        PRODUCT_CARD_LIVE_REVALIDATION_PAUSED,
        PRODUCT_CARD_LIVE_LOCAL_REVALIDATION_CANARY,
        PRODUCT_CARD_LIVE_LOCAL_SCHEDULER_ACTIVE,
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
