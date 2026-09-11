"""Fail-closed review packet for a future affiliate Pages route deployment."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

import affiliate_d1_production_state


VERSION = "0.1"
READY = "READY_FOR_SEPARATE_DEPLOYMENT_APPROVAL"
BLOCKED = "BLOCKED"
FAIL_CLOSED = "FAIL_CLOSED"
ROOT = Path(__file__).resolve().parents[1]


def _worker_rate_limit_candidate_present() -> bool:
    path = ROOT / "deployment-candidates" / "affiliate-worker" / "wrangler.toml"
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return False
    required = (
        'name = "AFFILIATE_CLIENT_RATE_LIMITER"',
        'namespace_id = "1001"',
        "limit = 10",
        "period = 60",
        "workers_dev = false",
        "preview_urls = false",
    )
    return all(value in content for value in required)


@dataclass(frozen=True)
class RouteDeploymentEvidence:
    candidate_chain_reviewed: bool
    current_workers_types_reviewed: bool
    d1_lookup_ready: bool
    secret_binding_names_ready: bool
    pages_function_entrypoint_present: bool
    rate_limit_binding_configured: bool
    trusted_opaque_client_key_derivation_present: bool
    workers_runtime_provider_present: bool
    proximate_pr_disclosure_connected: bool
    rollback_plan_recorded: bool
    free_plan_boundary_confirmed: bool
    production_deployment_performed: bool


@dataclass(frozen=True)
class RouteDeploymentReviewResult:
    version: str
    status: str
    deployment_review_candidate: bool
    production_deployment_allowed: bool
    route_activation_allowed: bool
    affiliate_activation_allowed: bool
    paid_plan_change_allowed: bool
    d1_lookup_ready: bool
    secret_binding_names_ready: bool
    runtime_boundary_ready: bool
    rollback_ready: bool
    reason_codes: tuple[str, ...]
    next_actions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        value["next_actions"] = list(self.next_actions)
        return value


def current_evidence() -> RouteDeploymentEvidence:
    """Compose sanitized repository and operator-reviewed facts only."""

    d1_state = affiliate_d1_production_state.assess(
        affiliate_d1_production_state.current_evidence()
    )
    return RouteDeploymentEvidence(
        candidate_chain_reviewed=True,
        current_workers_types_reviewed=True,
        d1_lookup_ready=d1_state.lookup_ready is True,
        # Pages secret names do not prove that the dedicated Worker owns the
        # same encrypted bindings. Keep this closed until names-only Worker
        # evidence confirms all three Worker-specific secrets.
        secret_binding_names_ready=False,
        pages_function_entrypoint_present=(
            (ROOT / "runtime-candidates" / "affiliate-pages-entrypoint-candidate.mjs").is_file()
            and (ROOT / "docs" / "policies" / "affiliate-pages-entrypoint-candidate-v0.1.md").is_file()
            and not (ROOT / "functions").exists()
        ),
        rate_limit_binding_configured=_worker_rate_limit_candidate_present(),
        trusted_opaque_client_key_derivation_present=(
            (ROOT / "runtime-candidates" / "affiliate-client-key-derivation.mjs").is_file()
            and (ROOT / "docs" / "policies" / "affiliate-client-key-derivation-candidate-v0.1.md").is_file()
        ),
        workers_runtime_provider_present=(
            (ROOT / "runtime-candidates" / "affiliate-workers-dmm-provider.mjs").is_file()
            and (ROOT / "docs" / "policies" / "affiliate-workers-dmm-provider-candidate-v0.1.md").is_file()
        ),
        proximate_pr_disclosure_connected=(
            (ROOT / "runtime-candidates" / "affiliate-cta-dom-renderer.mjs").is_file()
            and (ROOT / "docs" / "policies" / "affiliate-cta-dom-renderer-candidate-v0.1.md").is_file()
        ),
        rollback_plan_recorded=(
            (ROOT / "scripts" / "affiliate_route_rollback_plan.py").is_file()
            and (ROOT / "docs" / "policies" / "affiliate-route-rollback-plan-v0.1.md").is_file()
        ),
        free_plan_boundary_confirmed=d1_state.free_plan_compatible is True,
        production_deployment_performed=False,
    )


def assess(evidence: Any) -> RouteDeploymentReviewResult:
    """Review readiness without accepting credentials, URLs, IDs, or code payloads."""

    try:
        if not isinstance(evidence, RouteDeploymentEvidence) or any(
            not isinstance(value, bool) for value in asdict(evidence).values()
        ):
            raise ValueError("invalid evidence")

        reasons: list[str] = []
        actions: list[str] = []
        checks = (
            (evidence.candidate_chain_reviewed, "CANDIDATE_CHAIN_NOT_REVIEWED", "REVIEW_FULL_CANDIDATE_CHAIN"),
            (evidence.current_workers_types_reviewed, "CURRENT_WORKERS_TYPES_NOT_REVIEWED", "REVIEW_CURRENT_WORKERS_TYPES"),
            (evidence.d1_lookup_ready, "D1_LOOKUP_NOT_READY", "VERIFY_D1_LOOKUP_STATE"),
            (evidence.secret_binding_names_ready, "SECRET_BINDING_NAMES_NOT_READY", "VERIFY_SECRET_BINDING_NAMES"),
            (evidence.pages_function_entrypoint_present, "PAGES_FUNCTION_ENTRYPOINT_NOT_PRESENT", "IMPLEMENT_ISOLATED_PAGES_FUNCTION_ENTRYPOINT"),
            (evidence.rate_limit_binding_configured, "RATE_LIMIT_BINDING_NOT_CONFIGURED", "CONFIGURE_FREE_PLAN_COMPATIBLE_RATE_LIMIT_BINDING"),
            (evidence.trusted_opaque_client_key_derivation_present, "TRUSTED_CLIENT_KEY_DERIVATION_NOT_PRESENT", "IMPLEMENT_PRIVACY_PRESERVING_CLIENT_KEY_DERIVATION"),
            (evidence.workers_runtime_provider_present, "WORKERS_RUNTIME_PROVIDER_NOT_PRESENT", "IMPLEMENT_SERVER_SIDE_WORKERS_DMM_PROVIDER"),
            (evidence.proximate_pr_disclosure_connected, "PROXIMATE_PR_DISCLOSURE_NOT_CONNECTED", "CONNECT_PROXIMATE_PR_DISCLOSURE"),
            (evidence.rollback_plan_recorded, "ROLLBACK_PLAN_NOT_RECORDED", "RECORD_ROUTE_ROLLBACK_PLAN"),
            (evidence.free_plan_boundary_confirmed, "FREE_PLAN_BOUNDARY_NOT_CONFIRMED", "STOP_AND_NOTIFY_BEFORE_BILLING_CHANGE"),
        )
        for passed, reason, action in checks:
            if not passed:
                reasons.append(reason)
                actions.append(action)
        if evidence.production_deployment_performed:
            reasons.append("UNAPPROVED_PRODUCTION_DEPLOYMENT_DETECTED")
            actions.append("STOP_AND_REVIEW_PRODUCTION_STATE")

        runtime_ready = all(
            (
                evidence.pages_function_entrypoint_present,
                evidence.rate_limit_binding_configured,
                evidence.trusted_opaque_client_key_derivation_present,
                evidence.workers_runtime_provider_present,
                evidence.proximate_pr_disclosure_connected,
            )
        )
        ready = not reasons
        return RouteDeploymentReviewResult(
            VERSION,
            READY if ready else BLOCKED,
            ready,
            False,
            False,
            False,
            False,
            evidence.d1_lookup_ready,
            evidence.secret_binding_names_ready,
            runtime_ready,
            evidence.rollback_plan_recorded,
            tuple(reasons) or ("ROUTE_DEPLOYMENT_PACKET_READY",),
            tuple(actions),
        )
    except Exception:
        return RouteDeploymentReviewResult(
            VERSION,
            FAIL_CLOSED,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            ("ROUTE_DEPLOYMENT_REVIEW_INTERNAL_ERROR",),
            (),
        )


def main() -> int:
    result = assess(current_evidence())
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {READY, BLOCKED} else 2


if __name__ == "__main__":
    raise SystemExit(main())
