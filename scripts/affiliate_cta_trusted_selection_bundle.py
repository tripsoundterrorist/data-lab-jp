"""Trusted, hash-pinned CTA selection state for inert click assessment.

Only the canonical one-shot preflight receipt may be converted into this
safe-to-inspect bundle.  It contains no selected identifiers, content IDs, or
affiliate URLs.  The click assessor accepts this bundle rather than any
caller-provided selection digest or selection list.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

import affiliate_cta_canonical_selection_preflight as preflight


CANONICALIZATION_VERSION = "data-lab-affiliate-cta-selection-v1"
EXACT_SELECTION_COUNT = 10
SELECTION_DIGEST = "06c64c9dcc53e51f7767e86bfee39ae5e623bd0c66feebc840b940800c719fe3"
SOURCE_DATABASE_SHA256 = "9d2d0c0d0dc1ad74cadfb1d60374ccd12add8fe51a7dfc381eac8b735b5764f9"
LIVE_ARTIFACT_SHA256 = "862a2c275d0134856ecc9b095f9fe689903337c3c56c90e138dbb4a1e8a4022d"


@dataclass(frozen=True)
class TrustedSelectionBundle:
    """A public, non-identifying attestation of the one exact selection."""

    canonicalization_version: str
    selection_digest: str
    source_database_sha256: str
    live_artifact_sha256: str
    selected_count: int


@dataclass(frozen=True)
class TrustedResolverObservation:
    """Resolver-owned transient observation; never accepted as route input."""

    public_id: str
    selection_digest: str
    checked_at: datetime
    eligibility_status: str
    response: Mapping[str, Any]
    resolved_content_id: str


def from_canonical_preflight(receipt: Any) -> TrustedSelectionBundle | None:
    """Convert only the fixed, successful one-shot receipt into a bundle."""

    if type(receipt) is not preflight.CanonicalSelectionReceipt:
        return None
    if (
        receipt.version != preflight.VERSION
        or receipt.canonicalization_version != CANONICALIZATION_VERSION
        or receipt.status != preflight.READY
        or receipt.source_database_sha256 != SOURCE_DATABASE_SHA256
        or receipt.live_artifact_sha256 != LIVE_ARTIFACT_SHA256
        or receipt.selection_digest != SELECTION_DIGEST
        or receipt.submitted_count != EXACT_SELECTION_COUNT
        or receipt.selected_count != EXACT_SELECTION_COUNT
        or receipt.api_request_attempt_count != EXACT_SELECTION_COUNT
        or any((
            receipt.identifiers_exposed,
            receipt.affiliate_urls_exposed,
            receipt.production_write_performed,
            receipt.cta_activation_allowed,
            receipt.d1_write_allowed,
            receipt.deployment_allowed,
        ))
    ):
        return None
    return TrustedSelectionBundle(
        CANONICALIZATION_VERSION,
        SELECTION_DIGEST,
        SOURCE_DATABASE_SHA256,
        LIVE_ARTIFACT_SHA256,
        EXACT_SELECTION_COUNT,
    )


def valid_bundle(value: Any) -> bool:
    return type(value) is TrustedSelectionBundle and value == TrustedSelectionBundle(
        CANONICALIZATION_VERSION,
        SELECTION_DIGEST,
        SOURCE_DATABASE_SHA256,
        LIVE_ARTIFACT_SHA256,
        EXACT_SELECTION_COUNT,
    )


__all__ = [
    "CANONICALIZATION_VERSION", "EXACT_SELECTION_COUNT", "LIVE_ARTIFACT_SHA256",
    "SELECTION_DIGEST", "SOURCE_DATABASE_SHA256", "TrustedResolverObservation",
    "TrustedSelectionBundle", "from_canonical_preflight", "valid_bundle",
]
