"""Pure pre-transport safety contracts; no settings reads or network code."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from types import MappingProxyType
from typing import Any, Mapping

import affiliate_cta_approved_context as approved
import affiliate_cta_production_composition as composition


REQUIRED_SETTING_NAMES = frozenset({
    "DATA_LAB_CTA_APPROVED_PUBLIC_IDS",
    "DATA_LAB_CTA_SOURCE_DATABASE_SHA256",
    "DATA_LAB_CTA_LIVE_ARTIFACT_SHA256",
})
DISABLED = "DISABLED"
BLOCKED = "BLOCKED"
_LINE = re.compile(r"(itm_[0-9a-f]{24})\t([A-Za-z0-9][A-Za-z0-9_-]{0,127})\n\Z")


@dataclass(frozen=True)
class SafetyReceipt:
    status: str
    reason_codes: tuple[str, ...]
    transport_allowed: bool = False
    settings_values_exposed: bool = False
    production_write_performed: bool = False


class DisabledSettingsAdapter:
    """Schema-only adapter; values are deliberately neither loaded nor retained."""
    def required_names(self) -> frozenset[str]:
        return REQUIRED_SETTING_NAMES

    def read(self, _name: Any) -> None:
        return None

    def __repr__(self) -> str:
        return "<DisabledSettingsAdapter>"


class DisabledTransport:
    """No endpoint, credential, HTTP client, or retry capability exists here."""
    def request(self, _request: Any) -> None:
        return None

    def __repr__(self) -> str:
        return "<DisabledTransport>"


def kill_switch_state(value: Any) -> SafetyReceipt:
    if value is True:
        return SafetyReceipt(DISABLED, ("KILL_SWITCH_DISABLED",))
    return SafetyReceipt(BLOCKED, ("KILL_SWITCH_MISSING_OR_INVALID",))


def _owned_bytes(value: Any) -> bytes | None:
    if type(value) not in (bytes, bytearray):
        return None
    return bytes(value)


def _derive_mapping(source: bytes, context: Any) -> Mapping[str, str] | None:
    try:
        text = source.decode("ascii")
    except UnicodeDecodeError:
        return None
    lines = text.splitlines(keepends=True)
    if len(lines) != approved.EXACT_SELECTION_COUNT:
        return None
    pairs = [_LINE.fullmatch(line) for line in lines]
    if any(pair is None for pair in pairs):
        return None
    mapping = {pair.group(1): pair.group(2) for pair in pairs if pair is not None}
    if (
        len(mapping) != approved.EXACT_SELECTION_COUNT
        or tuple(mapping) != tuple(sorted(mapping))
        or set(mapping) != context.public_ids
        or len(set(mapping.values())) != approved.EXACT_SELECTION_COUNT
    ):
        return None
    return MappingProxyType(mapping)


def _verified_mapping_for_test(
    context: Any, source_bytes: Any, artifact_bytes: Any,
    expected_source_sha256: Any, expected_artifact_sha256: Any,
) -> Mapping[str, str] | None:
    """Fake-byte hash contract; production never reads files through this seam."""
    if (
        not approved._context_valid(context)
        or type(expected_source_sha256) is not str
        or type(expected_artifact_sha256) is not str
    ):
        return None
    source, artifact = _owned_bytes(source_bytes), _owned_bytes(artifact_bytes)
    if (
        source is None or artifact is None
        or hashlib.sha256(source).hexdigest() != expected_source_sha256
        or hashlib.sha256(artifact).hexdigest() != expected_artifact_sha256
    ):
        return None
    return _derive_mapping(source, context)


def _build_fake_lifecycle_for_test(
    *, context: Any, transport: Any, clock: Any,
    monotonic_clock: Any, deadline: Any,
    source_bytes: Any, artifact_bytes: Any,
    expected_source_sha256: Any, expected_artifact_sha256: Any,
    executor: Any = None, timeout_ms: Any = 1000,
) -> Any:
    """Internal-only review builder; failure precedes any transport request."""
    verified = _verified_mapping_for_test(
        context, source_bytes, artifact_bytes,
        expected_source_sha256, expected_artifact_sha256,
    )
    if verified is None or not callable(transport):
        return None
    try:
        return composition._build_offline_composition_for_test(
            context, verified, transport, clock,
            monotonic_clock=monotonic_clock, deadline=deadline,
            executor=executor, timeout_ms=timeout_ms,
        )
    except Exception:
        return None
