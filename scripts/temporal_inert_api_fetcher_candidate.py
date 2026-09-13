"""Inert request/response boundary for a future temporal DMM API fetcher.

This module cannot perform HTTP and cannot load credentials.  It prepares only
the public portion of one fixed request and reduces an already-supplied payload
to the exact isolated-bridge response shape.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from temporal_runbook_policy import FIXED_POPULATIONS


VERSION = "0.1-candidate"
ENDPOINT = "https://api.dmm.com/affiliate/v3/ItemList"
METHOD = "GET"
ACCEPT = "application/json"
TIMEOUT_SECONDS = 15
OUTPUT = "json"
CREDENTIAL_PARAMETER_NAMES = ("api_id", "affiliate_id")
NEXT_GATE = "REVIEW_INERT_TEMPORAL_API_FETCHER_CANDIDATE"
ALLOWED_IDENTITIES = frozenset(FIXED_POPULATIONS)
REQUEST_QUERY_FIELDS = frozenset(
    {"site", "service", "floor", "sort", "offset", "hits", "output"}
)


@dataclass(frozen=True)
class InertRequest:
    version: str
    endpoint: str
    method: str
    accept: str
    timeout_seconds: int
    query: dict[str, str | int]
    credential_parameter_names: tuple[str, ...]
    executable: bool
    live_api_request_authorized: bool
    credentials_access_authorized: bool
    state_write_authorized: bool
    scheduler_change_authorized: bool
    production_write_authorized: bool
    deploy_allowed: bool
    next_gate: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["credential_parameter_names"] = list(
            self.credential_parameter_names
        )
        return value


def _valid_identity(identity: Any) -> bool:
    return (
        isinstance(identity, tuple)
        and len(identity) == 3
        and isinstance(identity[0], str)
        and type(identity[1]) is int
        and type(identity[2]) is int
        and identity in ALLOWED_IDENTITIES
    )


def prepare_request(identity: Any) -> InertRequest:
    """Prepare public request facts without credentials or execution ability."""

    if not _valid_identity(identity):
        raise ValueError("REQUEST_NOT_ALLOWED")
    source_sort, offset, hits = identity
    query: dict[str, str | int] = {
        "site": "FANZA",
        "service": "digital",
        "floor": "videoa",
        "sort": source_sort,
        "offset": offset,
        "hits": hits,
        "output": OUTPUT,
    }
    if set(query) != REQUEST_QUERY_FIELDS:
        raise RuntimeError("INERT_REQUEST_CONTRACT_ERROR")
    return InertRequest(
        VERSION, ENDPOINT, METHOD, ACCEPT, TIMEOUT_SECONDS, query,
        CREDENTIAL_PARAMETER_NAMES, False, False, False, False, False, False,
        False, NEXT_GATE,
    )


def _bridge_failure(identity: tuple[str, int, int], code: str) -> dict[str, Any]:
    return {
        "request": {
            "source_sort": identity[0], "offset": identity[1], "hits": identity[2]
        },
        "success": False,
        "result_count": 0,
        "items": [],
        "error_classification": code,
    }


def classify_transport_failure(identity: Any, failure: Any) -> dict[str, Any]:
    """Convert a caller-classified failure without accepting exception text."""

    if not _valid_identity(identity):
        raise ValueError("REQUEST_NOT_ALLOWED")
    if isinstance(failure, str) and failure == "RATE_LIMIT":
        return _bridge_failure(identity, "RATE_LIMIT")
    if isinstance(failure, str) and failure in {"TIMEOUT", "NETWORK", "HTTP"}:
        return _bridge_failure(identity, "HTTP_ERROR")
    return _bridge_failure(identity, "API_ERROR")


def _bounded_integer(value: Any, *, maximum: int) -> int:
    if type(value) is int:
        parsed = value
    elif isinstance(value, str) and value.isascii() and value.isdigit():
        parsed = int(value)
    else:
        raise ValueError("API_RESPONSE_INVALID")
    if parsed < 0 or parsed > maximum:
        raise ValueError("API_RESPONSE_INVALID")
    return parsed


def reduce_response(
    identity: Any, *, http_status: Any, payload: Any
) -> dict[str, Any]:
    """Reduce a supplied DMM-shaped payload to the isolated bridge contract."""

    if not _valid_identity(identity):
        raise ValueError("REQUEST_NOT_ALLOWED")
    if type(http_status) is not int:
        return _bridge_failure(identity, "HTTP_ERROR")
    if http_status == 429:
        return _bridge_failure(identity, "RATE_LIMIT")
    if not 200 <= http_status < 300:
        return _bridge_failure(identity, "HTTP_ERROR")
    try:
        if not isinstance(payload, Mapping) or set(payload) != {"result"}:
            raise ValueError("API_RESPONSE_INVALID")
        result = payload["result"]
        if not isinstance(result, Mapping) or str(result.get("status")) != "200":
            raise ValueError("API_RESPONSE_INVALID")
        result_count = _bounded_integer(
            result.get("result_count"), maximum=identity[2]
        )
        items = result.get("items")
        if not isinstance(items, list) or len(items) != result_count:
            raise ValueError("API_RESPONSE_INVALID")
        reduced_items: list[dict[str, str]] = []
        for item in items:
            if not isinstance(item, Mapping):
                raise ValueError("API_RESPONSE_INVALID")
            content_id = item.get("content_id")
            if not isinstance(content_id, str) or not content_id.strip():
                raise ValueError("API_RESPONSE_INVALID")
            reduced_items.append({"content_id": content_id})
        return {
            "request": {
                "source_sort": identity[0],
                "offset": identity[1],
                "hits": identity[2],
            },
            "success": True,
            "result_count": result_count,
            "items": reduced_items,
            "error_classification": None,
        }
    except Exception:
        return _bridge_failure(identity, "API_ERROR")


__all__ = [
    "ACCEPT", "CREDENTIAL_PARAMETER_NAMES", "ENDPOINT", "InertRequest",
    "METHOD", "NEXT_GATE", "OUTPUT", "TIMEOUT_SECONDS", "VERSION",
    "classify_transport_failure", "prepare_request", "reduce_response",
]
