"""Inert route-to-click-decision composition for activation review only.

No callback, HTTP client, database, redirect emitter, CLI, or deployment entry
point exists here.  Only a trusted resolver may hold a transient identifier or
URL, the safe receipt exposes neither, and every activation capability remains
false.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import affiliate_runtime_route_contract as route
import affiliate_cta_click_revalidation_candidate as click


VERSION = "0.1-candidate"
READY = "READY_FOR_ACTIVATION_REVIEW"
BLOCKED = "BLOCKED"
FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class IntegrationReceipt:
    version: str
    status: str
    route_assessed: bool
    click_revalidation_assessed: bool
    response_status_candidate: int | None
    reason_codes: tuple[str, ...]
    redirect_location_present: bool = False
    redirect_activation_allowed: bool = False
    publication_allowed: bool = False
    gate_mutation_allowed: bool = False
    production_write_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _receipt(
    status: str,
    reasons: tuple[str, ...],
    *,
    click_assessed: bool = False,
    response_status: int | None = None,
) -> IntegrationReceipt:
    return IntegrationReceipt(
        VERSION,
        status,
        True,
        click_assessed,
        response_status,
        tuple(sorted(set(reasons))),
    )


def assess(
    *,
    version: Any,
    method: Any,
    path: Any,
    request_body_present: Any,
    official_answer_candidate: Any,
    publication_gate_overall_eligible: Any,
    runtime_chain_connected: Any,
    rate_limit_allowed: Any,
    pr_disclosure_available: Any,
    evaluated_at: Any,
) -> IntegrationReceipt:
    """Assess the existing route and click contracts without executing either."""

    try:
        if version != VERSION:
            return _receipt(FAIL_CLOSED, ("UNSUPPORTED_INTEGRATION_VERSION",))
        route_result = route.assess_route_request(
            route_version=route.ROUTE_VERSION,
            method=method,
            path=path,
            request_body_present=request_body_present,
            official_answer_candidate=official_answer_candidate,
            publication_gate_overall_eligible=publication_gate_overall_eligible,
            runtime_chain_connected=runtime_chain_connected,
            rate_limit_allowed=rate_limit_allowed,
            pr_disclosure_available=pr_disclosure_available,
        )
        if route_result.status != route.ROUTE_CANDIDATE:
            return _receipt(BLOCKED, tuple(route_result.reason_codes))

        public_id = path.removeprefix("/go/") if type(path) is str else None
        click_result = click.decide(
            version=click.VERSION,
            clicked_public_id=public_id,
            evaluated_at=evaluated_at,
        )
        if click_result.status != click.ALLOWED:
            return _receipt(BLOCKED, tuple(click_result.reason_codes), click_assessed=True)
        return _receipt(
            READY,
            ("ROUTE_CONTRACT_CONFIRMED",) + tuple(click_result.reason_codes),
            click_assessed=True,
            response_status=click_result.redirect_status_candidate,
        )
    except Exception:
        return _receipt(FAIL_CLOSED, ("INERT_INTEGRATION_INTERNAL_ERROR",))


__all__ = ["BLOCKED", "FAIL_CLOSED", "IntegrationReceipt", "READY", "VERSION", "assess"]
