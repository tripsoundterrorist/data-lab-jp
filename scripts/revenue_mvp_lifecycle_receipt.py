"""Shared sanitized lifecycle receipt contract for local Revenue MVP builds."""

from __future__ import annotations

import hashlib
from datetime import datetime

from product_verification import VerificationObservation
from revenue_mvp_official_lifecycle_policy import InventorySignal


LIFECYCLE_RECEIPT_VERSION = "0.2"
PUBLIC_ID_NAMESPACE = "data-lab-public-item-v0.1"
MAX_LIFECYCLE_FRESHNESS_AGE_SECONDS = 86400


def public_item_id(site: str, service: str, floor: str, content_id: str) -> str:
    source = "\0".join((PUBLIC_ID_NAMESPACE, site, service, floor, content_id))
    return "itm_" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:24]


class LifecycleReceipt:
    __slots__ = (
        "version",
        "public_id",
        "observation",
        "inventory_signal",
        "freshness_confirmed",
        "freshness_evaluated_at",
        "freshness_max_age_seconds",
    )

    def __init__(
        self,
        version: str,
        public_id: str,
        observation: VerificationObservation,
        inventory_signal: InventorySignal,
        freshness_confirmed: bool,
        freshness_evaluated_at: datetime | None = None,
        freshness_max_age_seconds: int | None = None,
    ) -> None:
        self.version = version
        self.public_id = public_id
        self.observation = observation
        self.inventory_signal = inventory_signal
        self.freshness_confirmed = freshness_confirmed
        self.freshness_evaluated_at = freshness_evaluated_at
        self.freshness_max_age_seconds = freshness_max_age_seconds


__all__ = [
    "LIFECYCLE_RECEIPT_VERSION",
    "LifecycleReceipt",
    "MAX_LIFECYCLE_FRESHNESS_AGE_SECONDS",
    "public_item_id",
]
