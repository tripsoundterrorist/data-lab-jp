"""Pure click-time revalidation decision candidate.

This module performs no lookup, HTTP request, redirect, logging, persistence,
Gate mutation, or activation.  A trusted caller may inject one transient API
observation; the returned receipt deliberately contains no identifier or URL.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import re
from typing import Any
from urllib.parse import urlsplit

import affiliate_link_adapter
from affiliate_link_policy import (
    CONDITIONALLY_APPROVED,
    LIFECYCLE_RESOLVED,
    VERIFICATION_PASS,
    WEB_UI,
)


VERSION = "0.1-candidate"
SELECTION_DIGEST = "ba7cbba3e5831ed8a26f25653db0865672b236ed96b372ea93877bdcdf5aac0b"
PUBLIC_ID = re.compile(r"itm_[0-9a-f]{24}\Z")
MAX_ITEMS = 10
MAX_AGE = timedelta(minutes=15)
ALLOWED_AFFILIATE_HOSTS = frozenset({"al.dmm.co.jp", "al.fanza.co.jp"})
ALLOWED = "REDIRECT_CANDIDATE_ALLOWED"
BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ClickDecision:
    version: str
    status: str
    reason_codes: tuple[str, ...]
    redirect_status_candidate: int | None
    redirect_location_present: bool = False
    redirect_activation_allowed: bool = False
    publication_allowed: bool = False
    gate_mutation_allowed: bool = False
    production_write_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(*reasons: str) -> ClickDecision:
    return ClickDecision(VERSION, BLOCKED, tuple(sorted(set(reasons))), None)


def decide(
    *,
    version: Any,
    selection_digest: Any,
    selected_public_ids: Any,
    clicked_public_id: Any,
    revalidation_status: Any,
    checked_at: Any,
    evaluated_at: Any,
    affiliate_url: Any,
) -> ClickDecision:
    """Return a bodyless 303 candidate receipt, never a redirect or URL."""

    try:
        if version != VERSION:
            return _blocked("UNSUPPORTED_VERSION")
        if selection_digest != SELECTION_DIGEST:
            return _blocked("SELECTION_DIGEST_MISMATCH")
        if type(selected_public_ids) is not tuple or not 1 <= len(selected_public_ids) <= MAX_ITEMS:
            return _blocked("SELECTION_INVALID")
        if any(type(value) is not str or PUBLIC_ID.fullmatch(value) is None for value in selected_public_ids):
            return _blocked("SELECTION_INVALID")
        if len(set(selected_public_ids)) != len(selected_public_ids):
            return _blocked("SELECTION_DUPLICATE")
        if type(clicked_public_id) is not str or PUBLIC_ID.fullmatch(clicked_public_id) is None:
            return _blocked("PUBLIC_ID_INVALID")
        if clicked_public_id not in selected_public_ids:
            return _blocked("PUBLIC_ID_NOT_IN_EXACT_SELECTION")
        if not isinstance(checked_at, datetime) or checked_at.tzinfo is None:
            return _blocked("CHECKED_AT_INVALID")
        if not isinstance(evaluated_at, datetime) or evaluated_at.tzinfo is None:
            return _blocked("EVALUATED_AT_INVALID")
        age = evaluated_at - checked_at
        if age < timedelta(0) or age > MAX_AGE:
            return _blocked("REVALIDATION_STALE_OR_FUTURE")
        if revalidation_status != "API_VISIBLE_AFFILIATE_PRESENT":
            return _blocked("REVALIDATION_NOT_ELIGIBLE")

        if type(affiliate_url) is not str:
            return _blocked("AFFILIATE_URL_INVALID")
        try:
            parsed_url = urlsplit(affiliate_url)
            affiliate_host = (parsed_url.hostname or "").casefold().rstrip(".")
        except (TypeError, ValueError):
            return _blocked("AFFILIATE_URL_INVALID")
        if affiliate_host not in ALLOWED_AFFILIATE_HOSTS or parsed_url.port is not None:
            return _blocked("AFFILIATE_URL_INVALID")

        link = affiliate_link_adapter.adapt_affiliate_link(
            adapter_version=affiliate_link_adapter.ADAPTER_VERSION,
            affiliate_url=affiliate_url,
            rights_status=CONDITIONALLY_APPROVED,
            publication_context=WEB_UI,
            lifecycle_status=LIFECYCLE_RESOLVED,
            verification_status=VERIFICATION_PASS,
            publication_gate_overall_eligible=True,
            pr_disclosure_available=True,
        )
        if link.validation_status != affiliate_link_adapter.VALID or link.production_render_allowed is not True:
            return _blocked("AFFILIATE_URL_INVALID")
        return ClickDecision(
            VERSION,
            ALLOWED,
            ("EXACT_SELECTION_CONFIRMED", "FRESH_API_REVALIDATION_CONFIRMED", "TRANSIENT_URL_VALIDATED"),
            303,
        )
    except Exception:
        return _blocked("CLICK_REVALIDATION_INTERNAL_ERROR")


__all__ = ["ALLOWED", "BLOCKED", "ClickDecision", "SELECTION_DIGEST", "VERSION", "decide"]
