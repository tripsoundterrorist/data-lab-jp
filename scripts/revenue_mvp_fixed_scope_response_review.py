"""Pure exact-item response decoder for mock/offline review only.

Caller-supplied identity and response are not trusted acquisition evidence.
No API, secrets, database, file, logging, redirect, rendering or scheduler use.
No response URL, source identifier or raw payload is retained in the receipt.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import re
from typing import Mapping

from affiliate_link_adapter import validate_affiliate_target
from revenue_mvp_lifecycle_receipt import public_item_id
from revenue_mvp_fixed_scope_refresh_review import Observation, image_valid, utc, MAX_AGE

CID = re.compile(r"[A-Za-z0-9._-]{1,128}\Z")
HOSTS = frozenset({"al.dmm.co.jp", "al.fanza.co.jp"})


@dataclass(frozen=True)
class DecodeResult:
    status: str
    reason_code: str
    observation: Observation | None = field(default=None, repr=False)
    price_is_lower_bound: bool | None = None
    trusted_acquisition_confirmed: bool = False
    api_calls: int = 0
    database_write_performed: bool = False
    publication_allowed: bool = False

    def summary(self):
        return {
            "status": self.status, "reason_code": self.reason_code,
            "observation_present": self.observation is not None,
            "price_is_lower_bound": self.price_is_lower_bound,
            "trusted_acquisition_confirmed": self.trusted_acquisition_confirmed,
            "api_calls": self.api_calls,
            "database_write_performed": self.database_write_performed,
            "publication_allowed": self.publication_allowed,
        }


def decode(*, target_public_id: str, resolved_content_id: str,
           payload: Mapping, http_status: int, observed_at: datetime,
           evaluated_at: datetime) -> DecodeResult:
    def blocked(reason):
        return DecodeResult("BLOCKED", reason)
    try:
        stamp, now = utc(observed_at), utc(evaluated_at)
        if not timedelta(0) <= now - stamp <= MAX_AGE:
            return blocked("OBSERVATION_STALE_OR_FUTURE")
        if (type(resolved_content_id) is not str or not CID.fullmatch(resolved_content_id)
                or type(target_public_id) is not str
                or public_item_id("FANZA", "digital", "videoa", resolved_content_id)
                != target_public_id):
            return blocked("EXACT_IDENTITY_BINDING_INVALID")
        if http_status == 429 and type(http_status) is int:
            return blocked("STOP_RATE_LIMIT")
        if type(http_status) is not int or http_status != 200 or not isinstance(payload, Mapping):
            return blocked("UPSTREAM_UNCONFIRMED")
        result = payload.get("result")
        if not isinstance(result, Mapping):
            return blocked("RESPONSE_INVALID")
        if type(result.get("status")) is not int:
            return blocked("RESPONSE_INVALID")
        if result["status"] == 429:
            return blocked("STOP_RATE_LIMIT")
        if result["status"] != 200:
            return blocked("UPSTREAM_UNCONFIRMED")
        items = result.get("items")
        count, total = result.get("result_count"), result.get("total_count")
        if (type(items) is not list or type(count) is not int or type(total) is not int
                or count != len(items) or total < count or count not in (0, 1)):
            return blocked("RESPONSE_COUNT_INVALID")
        if count == 0:
            if total != 0:
                return blocked("RESPONSE_COUNT_INVALID")
            return blocked("NO_MATCH_REQUIRES_SEPARATE_REVIEW")
        if total != 1:
            return blocked("EXACT_MATCH_NOT_UNIQUE")
        item = items[0]
        if (not isinstance(item, Mapping) or item.get("content_id") != resolved_content_id
                or item.get("service_code") != "digital"
                or item.get("floor_code") != "videoa"):
            return blocked("EXACT_ITEM_MISMATCH")
        if not validate_affiliate_target(item.get("affiliateURL"), allowed_hosts=HOSTS):
            return blocked("AFFILIATE_ELIGIBILITY_UNCONFIRMED")
        prices, images = item.get("prices"), item.get("imageURL")
        if not isinstance(prices, Mapping) or not isinstance(images, Mapping):
            return blocked("FIELD_MISSING")
        raw = prices.get("price")
        match = re.fullmatch(r"([0-9]{1,12})(~?)", raw.strip()) if type(raw) is str else None
        if match is None or not image_valid(images.get("large")):
            return blocked("FIELD_INVALID")
        observation = Observation(target_public_id, stamp, int(match[1]),
                                  images["large"], stamp, stamp, stamp, "VALID")
        return DecodeResult("STRUCTURAL_OBSERVATION_READY",
                            "TRUSTED_TRANSPORT_AND_APPROVAL_REQUIRED",
                            observation, bool(match[2]))
    except (ValueError, TypeError, AttributeError, OverflowError):
        return blocked("INPUT_INVALID")
