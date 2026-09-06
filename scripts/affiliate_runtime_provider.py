"""Ephemeral affiliate URL delivery provider for a guarded Web UI runtime.

The URL is accepted only as a call argument. It is validated by the existing
adapter and is passed to a trusted synchronous emitter only after the existing
UI handoff allows rendering. It is never included in the safe result.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable

import affiliate_link_adapter
import affiliate_ui_handoff
from affiliate_link_policy import WEB_UI


PROVIDER_VERSION = "0.1"
BLOCKED = "BLOCKED"
DELIVERED = "DELIVERED"
FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class AffiliateRuntimeProviderResult:
    provider_version: str
    status: str
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
    attempted: bool = False,
    delivered: bool = False,
    reasons: tuple[str, ...],
) -> AffiliateRuntimeProviderResult:
    return AffiliateRuntimeProviderResult(
        PROVIDER_VERSION,
        status,
        attempted,
        delivered,
        False,
        tuple(sorted(set(reasons))),
    )


def deliver_affiliate_link(
    *,
    provider_version: Any,
    affiliate_url: Any,
    rights_status: Any,
    lifecycle_status: Any,
    verification_status: Any,
    publication_gate_overall_eligible: Any,
    pr_disclosure_available: Any,
    emit_redirect: Callable[[str], None],
) -> AffiliateRuntimeProviderResult:
    """Deliver a transient URL once, only after all delegated guards allow it."""

    try:
        if provider_version != PROVIDER_VERSION:
            return _result(
                FAIL_CLOSED, reasons=("UNSUPPORTED_PROVIDER_VERSION",)
            )
        if not callable(emit_redirect):
            return _result(
                FAIL_CLOSED, reasons=("REDIRECT_EMITTER_INVALID",)
            )

        adapter = affiliate_link_adapter.adapt_affiliate_link(
            adapter_version=affiliate_link_adapter.ADAPTER_VERSION,
            affiliate_url=affiliate_url,
            rights_status=rights_status,
            publication_context=WEB_UI,
            lifecycle_status=lifecycle_status,
            verification_status=verification_status,
            publication_gate_overall_eligible=publication_gate_overall_eligible,
            pr_disclosure_available=pr_disclosure_available,
        )
        handoff = affiliate_ui_handoff.build_ui_handoff(
            handoff_version=affiliate_ui_handoff.HANDOFF_VERSION,
            adapter_result=adapter.to_dict(),
            target_context=affiliate_ui_handoff.WEB_UI,
            disclosure_available=pr_disclosure_available,
        )
        reasons = tuple(adapter.reason_codes) + tuple(handoff.reason_codes)
        if handoff.render_allowed is not True:
            return _result(BLOCKED, reasons=reasons)

        try:
            emit_redirect(affiliate_url)
        except Exception:
            return _result(
                FAIL_CLOSED,
                attempted=True,
                reasons=("REDIRECT_DELIVERY_FAILED",),
            )
        return _result(
            DELIVERED,
            attempted=True,
            delivered=True,
            reasons=("AFFILIATE_URL_DELIVERED_TO_TRUSTED_EMITTER",),
        )
    except Exception:
        return _result(
            FAIL_CLOSED, reasons=("AFFILIATE_RUNTIME_PROVIDER_INTERNAL_ERROR",)
        )


__all__ = [
    "AffiliateRuntimeProviderResult",
    "BLOCKED",
    "DELIVERED",
    "FAIL_CLOSED",
    "PROVIDER_VERSION",
    "deliver_affiliate_link",
]
