"""Network-disabled ItemList adapter candidate from confirmed minimum wire evidence.

It builds only a redacted request shape and parses synthetic fixtures. No query
string is completed, no secret value is accepted, and no network path exists.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import affiliate_cta_presentation as presentation
import affiliate_cta_transport_capability_manifest as capability
import affiliate_link_adapter


METHOD = "GET"
ENDPOINT = "https://api.dmm.com/affiliate/v3/ItemList"
SITE = "FANZA"
SERVICE = "digital"
FLOOR = "videoa"
HITS = 1
OFFSET = 1
OUTPUT = "json"
ENCODING = "utf-8"
MAX_CONTENT_ID_LENGTH = 128
_CONTENT_ID = re.compile(r"[A-Za-z0-9._-]{1,128}\Z")
_PARAMETER_NAMES = (
    "api_id", "affiliate_id", "site", "service", "floor", "cid", "hits", "offset", "output",
)
_ALLOWED_RESPONSE_ROOT = frozenset({"result"})
_ALLOWED_RESULT = frozenset({"status", "result_count", "total_count", "first_position", "items"})
_ALLOWED_ITEM = frozenset({"content_id", "affiliateURL"})
# Local fixture bound only; it makes no claim about provider limits.
MAX_SYNTHETIC_TOTAL_COUNT = 100_000
_CTA_HOSTS = frozenset({"al.dmm.co.jp", "al.fanza.co.jp"})
EVIDENCE_PATH = "runtime/private/official-wire-contract-review.txt"
EVIDENCE_SHA256 = "72e3486589983e13389e8f3abd94c51ed7379bc89c9043e93cca17d14313ff19"
EVIDENCE_REVISION = "official-wire-addendum-20260923"


class _OpaqueSecretHandle:
    __slots__ = ("_kind",)

    def __new__(cls, _kind: Any):
        raise TypeError("OPAQUE_SECRET_HANDLE_FACTORY_REQUIRED")

    def __repr__(self) -> str:
        return "<OpaqueSecretHandle>"


def _secret_handles_for_test() -> tuple[_OpaqueSecretHandle, _OpaqueSecretHandle]:
    """Creates opaque handles only; no secret value is accepted or retained."""
    api = object.__new__(_OpaqueSecretHandle)
    affiliate = object.__new__(_OpaqueSecretHandle)
    object.__setattr__(api, "_kind", "api")
    object.__setattr__(affiliate, "_kind", "affiliate")
    return api, affiliate


@dataclass(frozen=True, repr=False)
class CreditDisclosureMetadata:
    evidence_revision: str
    credit_display_required: bool
    disclosure_policy_reference: str
    html_change_allowed: bool = False
    publication_allowed: bool = False

    def __repr__(self) -> str:
        return "<CreditDisclosureMetadata>"


@dataclass(frozen=True, repr=False)
class CanonicalRequestPlan:
    method: str
    endpoint: str
    encoding: str
    parameter_names: tuple[str, ...]
    site: str
    service: str
    floor: str
    hits: int
    offset: int
    output: str
    cid_present: bool
    cid_encoded_length: int
    query_completed: bool
    network_allowed: bool
    evidence_path: str
    evidence_sha256: str
    evidence_revision: str
    credit_metadata: CreditDisclosureMetadata

    def __repr__(self) -> str:
        return "<CanonicalRequestPlan>"


class ValidatedSyntheticFixtureObservation:
    """Opaque, memory-only result of one strict synthetic-fixture validation."""

    __slots__ = ("__content_id", "__affiliate_url")

    def __new__(cls, _content_id: Any, _affiliate_url: Any):
        raise TypeError("SYNTHETIC_OBSERVATION_FACTORY_REQUIRED")

    def __repr__(self) -> str:
        return "<FixtureObservation>"


def _validated_synthetic_observation(
    content_id: str, affiliate_url: str,
) -> ValidatedSyntheticFixtureObservation:
    observation = object.__new__(ValidatedSyntheticFixtureObservation)
    object.__setattr__(observation, "_ValidatedSyntheticFixtureObservation__content_id", content_id)
    object.__setattr__(observation, "_ValidatedSyntheticFixtureObservation__affiliate_url", affiliate_url)
    return observation


def production_adapter() -> None:
    """Production remains disabled regardless of confirmed offline evidence."""
    return None


def credit_disclosure_metadata() -> CreditDisclosureMetadata:
    """Reference existing disclosure policy without rendering or changing HTML."""
    return CreditDisclosureMetadata(
        EVIDENCE_REVISION, True, presentation.PRESENTATION_VERSION, False, False,
    )


def _build_canonical_plan_for_test(
    *, content_id: Any, api_handle: Any, affiliate_handle: Any,
) -> CanonicalRequestPlan | None:
    if not _content_id_valid(content_id) or not _secret_handles_valid(api_handle, affiliate_handle):
        return None
    encoded = _encode_cid_for_test(content_id)
    if encoded is None:
        return None
    return CanonicalRequestPlan(
        METHOD, ENDPOINT, ENCODING, _PARAMETER_NAMES, SITE, SERVICE, FLOOR, HITS, OFFSET, OUTPUT,
        True, len(encoded), False, False,
        EVIDENCE_PATH, EVIDENCE_SHA256, EVIDENCE_REVISION, credit_disclosure_metadata(),
    )


def _encode_cid_for_test(value: Any) -> str | None:
    """Pure UTF-8 escaping conformance seam; returned data is never a request URL."""
    if not _content_id_valid(value):
        return None
    try:
        return _escape_utf8_component_for_test(value)
    except Exception:
        return None


def _escape_utf8_component_for_test(value: Any) -> str | None:
    """Network-free UTF-8 percent-encoding conformance helper for synthetic tests."""
    if type(value) is not str or not value or len(value) > MAX_CONTENT_ID_LENGTH:
        return None
    try:
        allowed = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
        return "".join(chr(byte) if byte in allowed else f"%{byte:02X}" for byte in value.encode(ENCODING, "strict"))
    except Exception:
        return None


def validate_synthetic_fixture_for_offline_harness(
    payload: Any, requested_content_id: Any,
) -> ValidatedSyntheticFixtureObservation | None:
    """Validate one synthetic fixture for an offline-only opaque handoff."""
    return _parse_fixture_for_test(payload, requested_content_id)


def _parse_fixture_for_test(
    payload: Any, requested_content_id: Any,
) -> ValidatedSyntheticFixtureObservation | None:
    """Strict synthetic JSON-shaped response parser with no persistence or logging."""
    try:
        if not _content_id_valid(requested_content_id) or type(payload) is not dict:
            return None
        # Request echoes may contain credentials, so they are intentionally
        # forbidden. Extra keys at every reviewed level fail closed.
        if not _keys_exact(payload, _ALLOWED_RESPONSE_ROOT):
            return None
        result = payload["result"]
        if type(result) is not dict or not _keys_exact(result, _ALLOWED_RESULT):
            return None
        status = result["status"]
        result_count = result["result_count"]
        total_count = result["total_count"]
        first_position = result["first_position"]
        items = result["items"]
        if (
            type(status) is not int or status != 200
            or type(result_count) is not int or result_count != 1
            or type(first_position) is not int or first_position != 1
            or type(total_count) is not int or not 1 <= total_count <= MAX_SYNTHETIC_TOTAL_COUNT
            or type(items) is not list or len(items) != 1
        ):
            return None
        item = items[0]
        if type(item) is not dict or not _keys_exact(item, _ALLOWED_ITEM):
            return None
        content_id = item["content_id"]
        affiliate_url = item["affiliateURL"]
        if type(content_id) is not str or content_id != requested_content_id:
            return None
        if type(affiliate_url) is not str or not affiliate_url:
            return None
        if not affiliate_link_adapter.validate_affiliate_target(affiliate_url, allowed_hosts=_CTA_HOSTS):
            return None
        return _validated_synthetic_observation(content_id, affiliate_url)
    except Exception:
        return None


def _content_id_valid(value: Any) -> bool:
    return type(value) is str and _CONTENT_ID.fullmatch(value) is not None


def _secret_handles_valid(api_handle: Any, affiliate_handle: Any) -> bool:
    return (
        type(api_handle) is _OpaqueSecretHandle and type(affiliate_handle) is _OpaqueSecretHandle
        and api_handle._kind == "api" and affiliate_handle._kind == "affiliate"
        and api_handle is not affiliate_handle
    )


def _keys_exact(value: dict[Any, Any], allowed: frozenset[str]) -> bool:
    if len(value) != len(allowed):
        return False
    for key in value:
        if type(key) is not str or key not in allowed:
            return False
    return True


__all__ = [
    "CanonicalRequestPlan", "CreditDisclosureMetadata", "EVIDENCE_PATH", "EVIDENCE_REVISION",
    "METHOD", "OFFICIAL_WIRE_CONTRACT_VERSION", "ValidatedSyntheticFixtureObservation",
    "credit_disclosure_metadata", "production_adapter", "validate_synthetic_fixture_for_offline_harness",
]

# This candidate deliberately does not alter the unresolved production marker.
OFFICIAL_WIRE_CONTRACT_VERSION = capability.OFFICIAL_WIRE_CONTRACT_VERSION
