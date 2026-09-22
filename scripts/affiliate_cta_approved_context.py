"""Internal approved-selection context for inert CTA assessment.

Production entry points never accept a selection, digest, resolver, or API
observation.  The actual ten identifiers remain in protected runtime storage;
until that internal context is configured, every production assessment blocks.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from datetime import datetime
from typing import Any, Callable, Mapping

import affiliate_cta_exact_selection as exact


CANONICALIZATION_VERSION = "data-lab-affiliate-cta-selection-v1"
EXACT_SELECTION_COUNT = 10
SELECTION_DIGEST = "06c64c9dcc53e51f7767e86bfee39ae5e623bd0c66feebc840b940800c719fe3"
SOURCE_DATABASE_SHA256 = "9d2d0c0d0dc1ad74cadfb1d60374ccd12add8fe51a7dfc381eac8b735b5764f9"
LIVE_ARTIFACT_SHA256 = "862a2c275d0134856ecc9b095f9fe689903337c3c56c90e138dbb4a1e8a4022d"


@dataclass(frozen=True)
class _TestOnlyApprovedContext:
    public_ids: frozenset[str]
    selection_digest: str
    observe: Callable[[str], Any]


@dataclass(frozen=True)
class _RuntimeApprovedContext:
    public_ids: frozenset[str]


@dataclass(frozen=True)
class _InternalObservation:
    """Atomic provider result: resolution, response, and observation time."""

    public_id: str
    selection_digest: str
    checked_at: datetime
    resolved_content_id: str
    response: Mapping[str, Any]


@dataclass(frozen=True)
class _InternalPresentationRecord:
    public_id: str
    selection_digest: str
    title: str
    observation: _InternalObservation


def production_context() -> _RuntimeApprovedContext | None:
    """Load only protected runtime configuration and re-derive its fixed digest."""
    raw = os.environ.get("DATA_LAB_CTA_APPROVED_PUBLIC_IDS")
    if (
        type(raw) is not str
        or os.environ.get("DATA_LAB_CTA_SOURCE_DATABASE_SHA256") != SOURCE_DATABASE_SHA256
        or os.environ.get("DATA_LAB_CTA_LIVE_ARTIFACT_SHA256") != LIVE_ARTIFACT_SHA256
    ):
        return None
    public_ids = tuple(raw.split(","))
    try:
        if (
            len(public_ids) != EXACT_SELECTION_COUNT
            or exact.canonical_digest(public_ids) != SELECTION_DIGEST
        ):
            return None
    except ValueError:
        return None
    return _RuntimeApprovedContext(frozenset(public_ids))


def production_observe(_public_id: str) -> None:
    """No resolver/fetch path is installed before official approval."""
    return None


def production_render_records() -> None:
    """No presentation provider is installed before official approval."""
    return None


def _make_test_context(public_ids: Any, observe: Any) -> _TestOnlyApprovedContext:
    """Internal test boundary; this is not called by production entry points."""
    if not callable(observe):
        raise ValueError("TEST_CONTEXT_INVALID")
    digest = exact.canonical_digest(public_ids)
    if len(public_ids) != EXACT_SELECTION_COUNT:
        raise ValueError("TEST_CONTEXT_INVALID")
    return _TestOnlyApprovedContext(frozenset(public_ids), digest, observe)


def _context_member(context: Any, public_id: Any) -> bool:
    return (
        type(context) in (_TestOnlyApprovedContext, _RuntimeApprovedContext)
        and type(public_id) is str
        and public_id in context.public_ids
        and len(context.public_ids) == EXACT_SELECTION_COUNT
        and (
            (type(context) is _RuntimeApprovedContext and exact.canonical_digest(tuple(context.public_ids)) == SELECTION_DIGEST)
            or (type(context) is _TestOnlyApprovedContext and exact.canonical_digest(tuple(context.public_ids)) == context.selection_digest)
        )
    )


def _context_digest(context: Any) -> str | None:
    if type(context) is _RuntimeApprovedContext:
        return SELECTION_DIGEST
    if type(context) is _TestOnlyApprovedContext:
        return context.selection_digest
    return None


__all__ = [
    "CANONICALIZATION_VERSION", "EXACT_SELECTION_COUNT", "LIVE_ARTIFACT_SHA256",
    "SELECTION_DIGEST", "SOURCE_DATABASE_SHA256", "production_context",
    "production_observe", "production_render_records",
]
