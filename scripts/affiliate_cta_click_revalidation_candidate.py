"""Pure click-time revalidation decision candidate.

This module performs no lookup, HTTP request, redirect, logging, persistence,
Gate mutation, or activation.  A trusted caller may inject one transient API
observation; the returned receipt deliberately contains no identifier or URL.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping
from urllib.parse import urlsplit

import affiliate_link_adapter
import affiliate_cta_exact_selection as exact_selection
from affiliate_link_policy import (
    CONDITIONALLY_APPROVED,
    LIFECYCLE_RESOLVED,
    VERIFICATION_PASS,
    WEB_UI,
)


VERSION = "0.1-candidate"
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
    observation: Any,
    evaluated_at: Any,
) -> ClickDecision:
    """Return a bodyless 303 candidate receipt, never a redirect or URL."""

    try:
        if version != VERSION:
            return _blocked("UNSUPPORTED_VERSION")
        try:
            if not exact_selection.verify(selected_public_ids, selection_digest):
                return _blocked("SELECTION_DIGEST_MISMATCH")
        except ValueError as error:
            return _blocked(str(error))
        if type(clicked_public_id) is not str or exact_selection.PUBLIC_ID.fullmatch(clicked_public_id) is None:
            return _blocked("PUBLIC_ID_INVALID")
        if clicked_public_id not in selected_public_ids:
            return _blocked("PUBLIC_ID_NOT_IN_EXACT_SELECTION")
        if not isinstance(evaluated_at, datetime) or evaluated_at.tzinfo is None:
            return _blocked("EVALUATED_AT_INVALID")
        if type(observation) is not dict or set(observation) != {
            "public_id", "resolved_content_id", "checked_at", "status", "response"
        }:
            return _blocked("OBSERVATION_INVALID")
        if observation["public_id"] != clicked_public_id:
            return _blocked("OBSERVATION_PUBLIC_ID_MISMATCH")
        content_id = observation["resolved_content_id"]
        if type(content_id) is not str or not content_id or len(content_id) > 128:
            return _blocked("RESOLVED_CONTENT_ID_INVALID")
        checked_at = observation["checked_at"]
        if not isinstance(checked_at, datetime) or checked_at.tzinfo is None:
            return _blocked("CHECKED_AT_INVALID")
        age = evaluated_at - checked_at
        if age < timedelta(0) or age > MAX_AGE:
            return _blocked("REVALIDATION_STALE_OR_FUTURE")
        if observation["status"] != "API_VISIBLE_AFFILIATE_PRESENT":
            return _blocked("REVALIDATION_NOT_ELIGIBLE")
        response = observation["response"]
        if not isinstance(response, Mapping):
            return _blocked("API_RESPONSE_INVALID")
        result = response.get("result")
        if not isinstance(result, Mapping) or str(result.get("status")) != "200":
            return _blocked("API_STATUS_INVALID")
        items = result.get("items")
        if not isinstance(items, list):
            return _blocked("API_ITEMS_INVALID")
        matches = [item for item in items if isinstance(item, Mapping) and item.get("content_id") == content_id]
        if len(matches) != 1:
            return _blocked("API_ITEM_MATCH_NOT_UNIQUE")
        affiliate_url = matches[0].get("affiliateURL")
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


__all__ = ["ALLOWED", "BLOCKED", "ClickDecision", "VERSION", "decide"]
