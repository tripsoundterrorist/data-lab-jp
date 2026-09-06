"""Read-only DMM callbacks for the guarded affiliate runtime resolver.

This module has no CLI and performs no publication or redirect. The database
lookup is query-only. The DMM response exists only as a return value to the
in-process resolver callback and is never logged or persisted here.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Callable, Mapping
import urllib.error
import urllib.parse
import urllib.request


CONNECTOR_VERSION = "0.1"
PUBLIC_ID_NAMESPACE = "data-lab-public-item-v0.1"
PUBLIC_ID = re.compile(r"itm_[0-9a-f]{24}\Z")
CONTENT_ID = re.compile(r"[A-Za-z0-9._-]{1,128}\Z")
ENDPOINT = "https://api.dmm.com/affiliate/v3/ItemList"
TIMEOUT_SECONDS = 15


class AffiliateRuntimeConnectorError(RuntimeError):
    """Bounded connector failure without upstream exception details."""


def _public_item_id(site: str, service: str, floor: str, content_id: str) -> str:
    source = "\0".join(
        (PUBLIC_ID_NAMESPACE, site, service, floor, content_id)
    )
    return "itm_" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:24]


def _load_env_value(path: Path, name: str) -> str | None:
    prefix = f"{name}="
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith(prefix):
            value = line[len(prefix):].strip()
            return value or None
    return None


def resolve_content_id(database_path: Path, public_id: str) -> str | None:
    """Resolve one public ID using a read-only SQLite connection."""

    if not isinstance(public_id, str) or not PUBLIC_ID.fullmatch(public_id):
        return None
    resolved = database_path.resolve()
    if not resolved.is_file():
        raise AffiliateRuntimeConnectorError("DATABASE_UNAVAILABLE")

    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(
            f"{resolved.as_uri()}?mode=ro", uri=True
        )
        connection.execute("PRAGMA query_only = ON")
        rows = connection.execute(
            "SELECT site, service, floor, content_id FROM items"
        )
        matches: list[str] = []
        for site, service, floor, content_id in rows:
            values = (site, service, floor, content_id)
            if not all(isinstance(value, str) for value in values):
                continue
            if not CONTENT_ID.fullmatch(content_id):
                continue
            if _public_item_id(site, service, floor, content_id) == public_id:
                matches.append(content_id)
                if len(matches) > 1:
                    return None
        return matches[0] if len(matches) == 1 else None
    except sqlite3.Error:
        raise AffiliateRuntimeConnectorError("DATABASE_READ_FAILED") from None
    finally:
        if connection is not None:
            connection.close()


def fetch_item_response(
    *,
    content_id: str,
    env_path: Path,
    fetcher: Callable[..., Any] = urllib.request.urlopen,
) -> Mapping[str, Any]:
    """Fetch exactly one item response without logging or persistence."""

    if not isinstance(content_id, str) or not CONTENT_ID.fullmatch(content_id):
        raise AffiliateRuntimeConnectorError("CONTENT_ID_INVALID")
    try:
        if not env_path.is_file():
            raise AffiliateRuntimeConnectorError("ENVIRONMENT_UNAVAILABLE")
        api_id = _load_env_value(env_path, "DMM_API_ID")
        affiliate_id = _load_env_value(env_path, "DMM_AFFILIATE_ID")
        if not api_id or not affiliate_id:
            raise AffiliateRuntimeConnectorError("ENVIRONMENT_UNAVAILABLE")

        parameters = {
            "api_id": api_id,
            "affiliate_id": affiliate_id,
            "site": "FANZA",
            "service": "digital",
            "floor": "videoa",
            "cid": content_id,
            "hits": 1,
            "offset": 1,
            "output": "json",
        }
        request = urllib.request.Request(
            ENDPOINT + "?" + urllib.parse.urlencode(parameters),
            headers={"Accept": "application/json"},
            method="GET",
        )
        with fetcher(request, timeout=TIMEOUT_SECONDS) as response:
            if not isinstance(response.status, int) or not 200 <= response.status < 300:
                raise AffiliateRuntimeConnectorError("API_HTTP_STATUS_INVALID")
            payload = json.load(response)
        if not isinstance(payload, Mapping):
            raise AffiliateRuntimeConnectorError("API_RESPONSE_INVALID")
        return payload
    except AffiliateRuntimeConnectorError:
        raise
    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        OSError,
    ):
        raise AffiliateRuntimeConnectorError("API_REQUEST_FAILED") from None
    except Exception:
        raise AffiliateRuntimeConnectorError("CONNECTOR_INTERNAL_ERROR") from None


__all__ = [
    "AffiliateRuntimeConnectorError",
    "CONNECTOR_VERSION",
    "fetch_item_response",
    "resolve_content_id",
]
