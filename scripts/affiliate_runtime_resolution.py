"""Read-only affiliate runtime resolution orchestration.

This module owns no database or HTTP client. Trusted callbacks resolve a public
item identifier and fetch one DMM API response. Internal identifiers and the
affiliate URL remain ephemeral and are never included in the safe result.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Callable, Mapping

import affiliate_runtime_provider
from affiliate_link_policy import (
    CONDITIONALLY_APPROVED,
    LIFECYCLE_RESOLVED,
    VERIFICATION_PASS,
)


RESOLUTION_VERSION = "0.1"
BLOCKED = "BLOCKED"
DELIVERED = "DELIVERED"
FAIL_CLOSED = "FAIL_CLOSED"
PUBLIC_ID = re.compile(r"itm_[0-9a-f]{24}\Z")
CONTENT_ID = re.compile(r"[A-Za-z0-9._-]{1,128}\Z")


@dataclass(frozen=True)
class AffiliateRuntimeResolutionResult:
    resolution_version: str
    status: str
    item_lookup_attempted: bool
    api_request_attempted: bool
    delivery_attempted: bool
    delivered: bool
    production_write_performed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(
    status: str,
    *,
    lookup: bool = False,
    requested: bool = False,
    delivery_attempted: bool = False,
    delivered: bool = False,
    reasons: tuple[str, ...],
) -> AffiliateRuntimeResolutionResult:
    return AffiliateRuntimeResolutionResult(
        RESOLUTION_VERSION,
        status,
        lookup,
        requested,
        delivery_attempted,
        delivered,
        False,
        tuple(sorted(set(reasons))),
    )


def _preflight(
    *,
    resolution_version: Any,
    public_id: Any,
    rights_status: Any,
    lifecycle_status: Any,
    verification_status: Any,
    publication_gate_overall_eligible: Any,
    pr_disclosure_available: Any,
    resolve_content_id: Any,
    fetch_item_response: Any,
    emit_redirect: Any,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if resolution_version != RESOLUTION_VERSION:
        reasons.append("UNSUPPORTED_RESOLUTION_VERSION")
    if not isinstance(public_id, str) or not PUBLIC_ID.fullmatch(public_id):
        reasons.append("PUBLIC_ID_INVALID")
    if rights_status != CONDITIONALLY_APPROVED:
        reasons.append("RIGHTS_NOT_CONDITIONALLY_APPROVED")
    if lifecycle_status != LIFECYCLE_RESOLVED:
        reasons.append("LIFECYCLE_SEMANTICS_PENDING")
    if verification_status != VERIFICATION_PASS:
        reasons.append("VERIFICATION_NOT_PASSED")
    if publication_gate_overall_eligible is not True:
        reasons.append("PUBLICATION_GATE_CLOSED")
    if pr_disclosure_available is not True:
        reasons.append("PR_DISCLOSURE_UNAVAILABLE")
    if not callable(resolve_content_id):
        reasons.append("ITEM_RESOLVER_INVALID")
    if not callable(fetch_item_response):
        reasons.append("API_FETCHER_INVALID")
    if not callable(emit_redirect):
        reasons.append("REDIRECT_EMITTER_INVALID")
    return tuple(reasons)


def _affiliate_url_from_response(
    response: Any, expected_content_id: str
) -> tuple[str | None, tuple[str, ...]]:
    if not isinstance(response, Mapping):
        return None, ("API_RESPONSE_INVALID",)
    result = response.get("result")
    if not isinstance(result, Mapping) or str(result.get("status")) != "200":
        return None, ("API_STATUS_INVALID",)
    items = result.get("items")
    if not isinstance(items, list):
        return None, ("API_ITEMS_INVALID",)
    matches = [
        item for item in items
        if isinstance(item, Mapping)
        and item.get("content_id") == expected_content_id
    ]
    if len(matches) != 1:
        return None, ("API_ITEM_MATCH_NOT_UNIQUE",)
    value = matches[0].get("affiliateURL")
    if not isinstance(value, str) or not value:
        return None, ("API_AFFILIATE_LINK_UNAVAILABLE",)
    return value, ()


def resolve_and_deliver_affiliate_link(
    *,
    resolution_version: Any,
    public_id: Any,
    rights_status: Any,
    lifecycle_status: Any,
    verification_status: Any,
    publication_gate_overall_eligible: Any,
    pr_disclosure_available: Any,
    resolve_content_id: Callable[[str], str | None],
    fetch_item_response: Callable[[str], Mapping[str, Any]],
    emit_redirect: Callable[[str], None],
) -> AffiliateRuntimeResolutionResult:
    """Resolve, fetch and deliver without returning any identifier or URL."""

    try:
        blockers = _preflight(
            resolution_version=resolution_version,
            public_id=public_id,
            rights_status=rights_status,
            lifecycle_status=lifecycle_status,
            verification_status=verification_status,
            publication_gate_overall_eligible=publication_gate_overall_eligible,
            pr_disclosure_available=pr_disclosure_available,
            resolve_content_id=resolve_content_id,
            fetch_item_response=fetch_item_response,
            emit_redirect=emit_redirect,
        )
        if blockers:
            return _result(BLOCKED, reasons=blockers)

        try:
            content_id = resolve_content_id(public_id)
        except Exception:
            return _result(
                FAIL_CLOSED,
                lookup=True,
                reasons=("ITEM_RESOLUTION_FAILED",),
            )
        if not isinstance(content_id, str) or not CONTENT_ID.fullmatch(content_id):
            return _result(
                BLOCKED,
                lookup=True,
                reasons=("ITEM_NOT_RESOLVED",),
            )

        try:
            response = fetch_item_response(content_id)
        except Exception:
            return _result(
                FAIL_CLOSED,
                lookup=True,
                requested=True,
                reasons=("API_REQUEST_FAILED",),
            )
        affiliate_url, response_reasons = _affiliate_url_from_response(
            response, content_id
        )
        if affiliate_url is None:
            return _result(
                BLOCKED,
                lookup=True,
                requested=True,
                reasons=response_reasons,
            )

        delivery = affiliate_runtime_provider.deliver_affiliate_link(
            provider_version=affiliate_runtime_provider.PROVIDER_VERSION,
            affiliate_url=affiliate_url,
            rights_status=rights_status,
            lifecycle_status=lifecycle_status,
            verification_status=verification_status,
            publication_gate_overall_eligible=publication_gate_overall_eligible,
            pr_disclosure_available=pr_disclosure_available,
            emit_redirect=emit_redirect,
        )
        return _result(
            DELIVERED if delivery.delivered else (
                FAIL_CLOSED
                if delivery.status == affiliate_runtime_provider.FAIL_CLOSED
                else BLOCKED
            ),
            lookup=True,
            requested=True,
            delivery_attempted=delivery.delivery_attempted,
            delivered=delivery.delivered,
            reasons=tuple(delivery.reason_codes),
        )
    except Exception:
        return _result(
            FAIL_CLOSED,
            reasons=("AFFILIATE_RUNTIME_RESOLUTION_INTERNAL_ERROR",),
        )


__all__ = [
    "AffiliateRuntimeResolutionResult",
    "BLOCKED",
    "DELIVERED",
    "FAIL_CLOSED",
    "RESOLUTION_VERSION",
    "resolve_and_deliver_affiliate_link",
]
