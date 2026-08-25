"""Ephemeral URL-validation adapter for Affiliate Link Policy v0.1.

The URL exists only as a local call argument while validation runs.  It is not
included in results, logs, exceptions, persistence, or policy input.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import re
from typing import Any
from urllib.parse import urlsplit

import affiliate_link_policy as link_policy


ADAPTER_VERSION = "0.1"
VALID = "VALID"
INVALID = "INVALID"
WINDOWS_PATH = re.compile(r"(?i)^[a-z]:[\\/]")


@dataclass(frozen=True)
class AffiliateLinkAdapterResult:
    adapter_version: str
    validation_status: str
    link_status: str
    ui_candidate: bool
    production_render_allowed: bool
    pr_disclosure_required: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **{key: value for key, value in self.__dict__.items() if key != "reason_codes"},
            "reason_codes": list(self.reason_codes),
        }


def _result(
    validation_status: str,
    link_status: str = link_policy.INVALID_INPUT,
    *,
    ui_candidate: bool = False,
    production_render_allowed: bool = False,
    pr_disclosure_required: bool = True,
    reasons: tuple[str, ...],
) -> AffiliateLinkAdapterResult:
    return AffiliateLinkAdapterResult(
        ADAPTER_VERSION, validation_status, link_status, ui_candidate,
        production_render_allowed, pr_disclosure_required,
        tuple(sorted(set(reasons))),
    )


def _validate_url(value: Any) -> tuple[bool, tuple[str, ...]]:
    if not isinstance(value, str) or not value:
        return False, ("URL_MALFORMED",)
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return False, ("URL_CONTROL_CHARACTER",)
    if any(character.isspace() for character in value):
        return False, ("URL_WHITESPACE_FORBIDDEN",)
    if value.startswith(("\\\\", "//")):
        return False, ("URL_UNC_FORBIDDEN",)
    if "\\" in value or WINDOWS_PATH.match(value):
        return False, ("URL_LOCAL_PATH_FORBIDDEN",)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError):
        return False, ("URL_MALFORMED",)
    if parsed.scheme.lower() not in {"http", "https"}:
        return False, ("URL_SCHEME_FORBIDDEN",)
    if not parsed.netloc or not parsed.hostname:
        return False, ("URL_HOST_REQUIRED",)
    if parsed.username is not None or parsed.password is not None:
        return False, ("URL_EMBEDDED_CREDENTIAL_FORBIDDEN",)
    hostname = parsed.hostname.casefold().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return False, ("URL_LOOPBACK_FORBIDDEN",)
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and address.is_loopback:
        return False, ("URL_LOOPBACK_FORBIDDEN",)
    if port is not None and not 1 <= port <= 65535:
        return False, ("URL_PORT_INVALID",)
    return True, ("LINK_VALUE_VALIDATED",)


def _adapt(
    *,
    adapter_version: Any,
    affiliate_url: Any,
    rights_status: Any,
    publication_context: Any,
    lifecycle_status: Any,
    verification_status: Any,
    publication_gate_overall_eligible: Any,
    pr_disclosure_available: Any,
) -> AffiliateLinkAdapterResult:
    if adapter_version != ADAPTER_VERSION:
        return _result(INVALID, reasons=("UNSUPPORTED_ADAPTER_VERSION",))
    if not isinstance(publication_gate_overall_eligible, bool):
        return _result(INVALID, reasons=("GATE_STATUS_MALFORMED",))
    valid, reasons = _validate_url(affiliate_url)
    if not valid:
        return _result(INVALID, reasons=reasons)
    policy_result = link_policy.assess_affiliate_link(
        policy_version=link_policy.POLICY_VERSION,
        rights_status=rights_status,
        publication_context=publication_context,
        has_affiliate_url=True,
        lifecycle_status=lifecycle_status,
        verification_status=verification_status,
        publication_gate_status=(
            link_policy.GATE_OPEN
            if publication_gate_overall_eligible
            else link_policy.GATE_CLOSED
        ),
        pr_disclosure_available=pr_disclosure_available,
    )
    return _result(
        VALID,
        policy_result.link_status,
        ui_candidate=policy_result.ui_candidate,
        production_render_allowed=(
            policy_result.production_render_allowed
            and publication_gate_overall_eligible
        ),
        pr_disclosure_required=policy_result.pr_disclosure_required,
        reasons=("LINK_VALUE_VALIDATED",) + policy_result.reason_codes,
    )


def adapt_affiliate_link(**kwargs: Any) -> AffiliateLinkAdapterResult:
    """Validate a transient URL and return only a bounded safe summary."""

    try:
        return _adapt(**kwargs)
    except Exception:
        return _result(INVALID, reasons=("INTERNAL_ADAPTER_ERROR",))


__all__ = [
    "ADAPTER_VERSION", "AffiliateLinkAdapterResult", "INVALID", "VALID",
    "adapt_affiliate_link",
]
