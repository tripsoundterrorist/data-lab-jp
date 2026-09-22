"""Canonical, order-independent binding for an exact CTA canary selection."""

from __future__ import annotations

import hashlib
import re
from typing import Any

PUBLIC_ID = re.compile(r"itm_[0-9a-f]{24}\Z")
MAX_ITEMS = 10
PREFIX = b"data-lab-affiliate-cta-selection-v1\n"


def canonical_digest(public_ids: Any) -> str:
    if type(public_ids) is not tuple or not 1 <= len(public_ids) <= MAX_ITEMS:
        raise ValueError("SELECTION_INVALID")
    if any(type(value) is not str or PUBLIC_ID.fullmatch(value) is None for value in public_ids):
        raise ValueError("SELECTION_INVALID")
    if len(set(public_ids)) != len(public_ids):
        raise ValueError("SELECTION_DUPLICATE")
    canonical = "\n".join(sorted(public_ids)).encode("ascii")
    return hashlib.sha256(PREFIX + canonical).hexdigest()


def verify(public_ids: Any, expected_digest: Any) -> bool:
    return type(expected_digest) is str and canonical_digest(public_ids) == expected_digest


__all__ = ["MAX_ITEMS", "PUBLIC_ID", "canonical_digest", "verify"]
