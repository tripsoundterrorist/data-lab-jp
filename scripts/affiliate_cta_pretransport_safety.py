"""Pure pre-transport safety contracts; no settings reads or network code."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
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


def _verified_mapping_for_test(
    context: Any, mapping: Any, source_bytes: Any, artifact_bytes: Any,
    expected_source_sha256: Any, expected_artifact_sha256: Any,
) -> Mapping[str, str] | None:
    """Fake-byte hash contract; production never reads files through this seam."""
    if (
        not approved._context_valid(context)
        or type(source_bytes) is not bytes
        or type(artifact_bytes) is not bytes
        or type(expected_source_sha256) is not str
        or type(expected_artifact_sha256) is not str
        or hashlib.sha256(source_bytes).hexdigest() != expected_source_sha256
        or hashlib.sha256(artifact_bytes).hexdigest() != expected_artifact_sha256
        or type(mapping) is not dict
        or set(mapping) != context.public_ids
        or len(set(mapping.values())) != approved.EXACT_SELECTION_COUNT
    ):
        return None
    return dict(mapping)


def _build_fake_lifecycle_for_test(
    *, context: Any, mapping: Any, transport: Any, clock: Any,
    source_bytes: Any, artifact_bytes: Any,
    expected_source_sha256: Any, expected_artifact_sha256: Any,
) -> Any:
    """Internal-only review builder; failure precedes any transport request."""
    verified = _verified_mapping_for_test(
        context, mapping, source_bytes, artifact_bytes,
        expected_source_sha256, expected_artifact_sha256,
    )
    if verified is None or not callable(transport):
        return None
    return composition._build_offline_composition_for_test(
        context, verified, transport, clock,
    )
