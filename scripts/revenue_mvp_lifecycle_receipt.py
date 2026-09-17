"""Shared sanitized lifecycle receipt contract for local Revenue MVP builds."""

from __future__ import annotations

import hashlib

from product_verification import VerificationObservation
from revenue_mvp_official_lifecycle_policy import InventorySignal


LIFECYCLE_RECEIPT_VERSION = "0.1"
PUBLIC_ID_NAMESPACE = "data-lab-public-item-v0.1"


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
    )

    def __init__(
        self,
        version: str,
        public_id: str,
        observation: VerificationObservation,
        inventory_signal: InventorySignal,
        freshness_confirmed: bool,
    ) -> None:
        self.version = version
        self.public_id = public_id
        self.observation = observation
        self.inventory_signal = inventory_signal
        self.freshness_confirmed = freshness_confirmed


__all__ = [
    "LIFECYCLE_RECEIPT_VERSION",
    "LifecycleReceipt",
    "public_item_id",
]
