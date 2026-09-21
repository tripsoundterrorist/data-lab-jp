"""Ephemeral affiliate URL validation for sanitized lifecycle evidence.

The URL value is accepted only as a call argument.  Results contain a
tri-state presence observation and a bounded reason code, never the URL.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit


ALLOWED_AFFILIATE_HOST_SUFFIXES = (
    "dmm.co.jp",
    "dmm.com",
    "fanza.com",
    "fanza.co.jp",
)


def observe_affiliate_url(value: Any) -> tuple[bool | None, str]:
    """Return safe presence evidence without retaining or returning the URL."""

    if value is None:
        return False, "AFFILIATE_URL_ABSENT"
    if not isinstance(value, str) or not value or value != value.strip():
        return None, "AFFILIATE_URL_VALIDATION_FAILED"
    if "\\" in value or any(character.isspace() for character in value):
        return None, "AFFILIATE_URL_VALIDATION_FAILED"
    if len(value) > 2048 or any(
        ord(character) < 33 or ord(character) == 127 for character in value
    ):
        return None, "AFFILIATE_URL_VALIDATION_FAILED"
    if re.search(r"%(?:00|0a|0d)", value, re.IGNORECASE):
        return None, "AFFILIATE_URL_VALIDATION_FAILED"
    try:
        parsed = urlsplit(value)
        hostname = (parsed.hostname or "").casefold().rstrip(".")
        if parsed.port not in (None, 443):
            return None, "AFFILIATE_URL_VALIDATION_FAILED"
    except (TypeError, ValueError):
        return None, "AFFILIATE_URL_VALIDATION_FAILED"
    host_allowed = bool(hostname) and any(
        hostname == suffix or hostname.endswith("." + suffix)
        for suffix in ALLOWED_AFFILIATE_HOST_SUFFIXES
    )
    if (
        parsed.scheme.casefold() != "https"
        or not host_allowed
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None, "AFFILIATE_URL_VALIDATION_FAILED"
    return True, "AFFILIATE_URL_VALIDATED"


__all__ = [
    "ALLOWED_AFFILIATE_HOST_SUFFIXES",
    "observe_affiliate_url",
]
