"""Non-deploying preflight for an affiliate redirect runtime candidate.

Only binding names and sanitized configuration facts are accepted. Secret values,
URLs returned by DMM, item identifiers, and credentials are never accepted.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
from typing import Any

import affiliate_d1_production_state
import revenue_mvp_official_answer_matrix


PREFLIGHT_VERSION = "0.4"
READY_FOR_DEPLOYMENT_REVIEW = "READY_FOR_DEPLOYMENT_REVIEW"
BLOCKED = "BLOCKED"
FAIL_CLOSED = "FAIL_CLOSED"

REQUIRED_SECRET_BINDINGS = frozenset({"DMM_API_ID", "DMM_AFFILIATE_ID"})
REQUIRED_DATA_BINDINGS = frozenset({"AFFILIATE_ITEM_LOOKUP"})
EXPECTED_ROUTE = "/go/:public_id"
EXPECTED_METHODS = frozenset({"GET", "HEAD"})
EXPECTED_REDIRECT_STATUS = 302
MAX_REQUESTS_PER_MINUTE = 60
MAX_BURST = 10
BINDING_NAME = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")


@dataclass(frozen=True)
class AffiliateDeploymentCandidate:
    platform_adapter_candidate: bool
    private_lookup_import_preflight_ready: bool
    secret_binding_names: tuple[str, ...]
    data_binding_names: tuple[str, ...]
    route_path: str | None
    allowed_methods: tuple[str, ...]
    redirect_status: int | None
    per_client_rate_limit: bool
    requests_per_minute: int | None
    burst_limit: int | None
    log_redaction_enabled: bool
    response_cache_disabled: bool
    official_answer_candidate: bool
    runtime_provider_connected: bool
    runtime_resolution_connected: bool
    pr_disclosure_available: bool


@dataclass(frozen=True)
class AffiliateDeploymentPreflightResult:
    preflight_version: str
    status: str
    deployment_candidate: bool
    production_deployment_allowed: bool
    platform_adapter_candidate: bool
    private_lookup_import_preflight_ready: bool
    secret_binding_name_count: int
    data_binding_name_count: int
    route_configured: bool
    rate_limit_configured: bool
    runtime_chain_connected: bool
    reason_codes: tuple[str, ...]
    next_actions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        value["next_actions"] = list(self.next_actions)
        return value


def current_input() -> AffiliateDeploymentCandidate:
    """Return the current fail-closed state without reading environment values."""

    d1_state = affiliate_d1_production_state.assess(
        affiliate_d1_production_state.current_evidence()
    )
    official_answers = revenue_mvp_official_answer_matrix.assess_answer_matrix(
        revenue_mvp_official_answer_matrix.current_entries()
    )

    return AffiliateDeploymentCandidate(
        platform_adapter_candidate=True,
        private_lookup_import_preflight_ready=(
            d1_state.status == affiliate_d1_production_state.READY
            and d1_state.lookup_ready is True
        ),
        secret_binding_names=(),
        data_binding_names=("AFFILIATE_ITEM_LOOKUP",),
        route_path=None,
        allowed_methods=(),
        redirect_status=None,
        per_client_rate_limit=False,
        requests_per_minute=None,
        burst_limit=None,
        log_redaction_enabled=False,
        response_cache_disabled=False,
        official_answer_candidate=(
            official_answers.core_publication_candidate is True
            and official_answers.gate_unlock_allowed is False
        ),
        runtime_provider_connected=False,
        runtime_resolution_connected=False,
        pr_disclosure_available=False,
    )


def _valid_names(value: Any) -> bool:
    return (
        isinstance(value, tuple)
        and all(isinstance(name, str) and BINDING_NAME.fullmatch(name) for name in value)
        and len(value) == len(set(value))
    )


def assess_preflight(
    candidate: AffiliateDeploymentCandidate,
) -> AffiliateDeploymentPreflightResult:
    """Assess names and safe facts only; never deploy or read a secret."""

    try:
        if not isinstance(candidate, AffiliateDeploymentCandidate):
            raise ValueError("invalid candidate")

        reasons: set[str] = set()
        actions: list[str] = []

        platform_ready = candidate.platform_adapter_candidate is True
        if not platform_ready:
            reasons.add("PLATFORM_ADAPTER_CANDIDATE_NOT_READY")
            actions.append("PREPARE_NON_DEPLOYED_PLATFORM_ADAPTER")

        lookup_preflight_ready = (
            candidate.private_lookup_import_preflight_ready is True
        )
        if not lookup_preflight_ready:
            reasons.add("PRIVATE_LOOKUP_IMPORT_PREFLIGHT_NOT_READY")
            actions.append("RUN_PRIVATE_LOOKUP_D1_IMPORT_PREFLIGHT")

        secret_names_valid = _valid_names(candidate.secret_binding_names)
        data_names_valid = _valid_names(candidate.data_binding_names)
        if not secret_names_valid or set(candidate.secret_binding_names) != REQUIRED_SECRET_BINDINGS:
            reasons.add("SECRET_BINDINGS_NOT_READY")
            actions.append("CONFIGURE_REQUIRED_SECRET_BINDINGS")
        if not data_names_valid or set(candidate.data_binding_names) != REQUIRED_DATA_BINDINGS:
            reasons.add("DATA_BINDING_NOT_READY")
            actions.append("CONFIGURE_PRIVATE_ITEM_LOOKUP")

        route_ready = (
            candidate.route_path == EXPECTED_ROUTE
            and isinstance(candidate.allowed_methods, tuple)
            and frozenset(candidate.allowed_methods) == EXPECTED_METHODS
            and len(candidate.allowed_methods) == len(EXPECTED_METHODS)
            and candidate.redirect_status == EXPECTED_REDIRECT_STATUS
        )
        if not route_ready:
            reasons.add("AFFILIATE_ROUTE_NOT_READY")
            actions.append("CONFIGURE_DEDICATED_GET_HEAD_ROUTE")

        rate_values_valid = all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in (candidate.requests_per_minute, candidate.burst_limit)
        )
        rate_ready = (
            candidate.per_client_rate_limit is True
            and rate_values_valid
            and 1 <= candidate.requests_per_minute <= MAX_REQUESTS_PER_MINUTE
            and 1 <= candidate.burst_limit <= MAX_BURST
            and candidate.burst_limit <= candidate.requests_per_minute
        )
        if not rate_ready:
            reasons.add("RATE_LIMIT_NOT_READY")
            actions.append("CONFIGURE_BOUNDED_PER_CLIENT_RATE_LIMIT")

        if candidate.log_redaction_enabled is not True:
            reasons.add("LOG_REDACTION_NOT_READY")
            actions.append("ENABLE_IDENTIFIER_AND_URL_LOG_REDACTION")
        if candidate.response_cache_disabled is not True:
            reasons.add("RESPONSE_CACHE_POLICY_NOT_READY")
            actions.append("DISABLE_AFFILIATE_REDIRECT_CACHE")
        if candidate.official_answer_candidate is not True:
            reasons.add("OFFICIAL_ANSWER_GATE_CLOSED")
            actions.append("VERIFY_PRODUCTION_DOMAIN_APPROVAL")
        runtime_ready = (
            candidate.runtime_provider_connected is True
            and candidate.runtime_resolution_connected is True
        )
        if not runtime_ready:
            reasons.add("AFFILIATE_RUNTIME_CHAIN_NOT_CONNECTED")
            actions.append("CONNECT_AFFILIATE_RUNTIME_CHAIN")
        if candidate.pr_disclosure_available is not True:
            reasons.add("PR_DISCLOSURE_NOT_READY")
            actions.append("ADD_PROXIMATE_PR_DISCLOSURE")

        ready = not reasons
        return AffiliateDeploymentPreflightResult(
            PREFLIGHT_VERSION,
            READY_FOR_DEPLOYMENT_REVIEW if ready else BLOCKED,
            ready,
            False,
            platform_ready,
            lookup_preflight_ready,
            len(candidate.secret_binding_names) if secret_names_valid else 0,
            len(candidate.data_binding_names) if data_names_valid else 0,
            route_ready,
            rate_ready,
            runtime_ready,
            tuple(sorted(reasons)) or ("AFFILIATE_DEPLOYMENT_PREFLIGHT_PASS",),
            tuple(dict.fromkeys(actions)),
        )
    except Exception:
        return AffiliateDeploymentPreflightResult(
            PREFLIGHT_VERSION,
            FAIL_CLOSED,
            False,
            False,
            False,
            False,
            0,
            0,
            False,
            False,
            False,
            ("AFFILIATE_DEPLOYMENT_PREFLIGHT_INTERNAL_ERROR",),
            (),
        )


def main() -> int:
    result = assess_preflight(current_input())
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {BLOCKED, READY_FOR_DEPLOYMENT_REVIEW} else 2


if __name__ == "__main__":
    raise SystemExit(main())
