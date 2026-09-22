"""Offline capability-manifest and activation-preflight contract.

This module deliberately has no endpoint, credential, settings-value, transport,
clock, logging, persistence, deployment, or activation capability.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any

from affiliate_cta_pretransport_safety import REQUIRED_SETTING_NAMES


CONTRACT_VERSION = "0.1"
UNCONFIRMED = "UNCONFIRMED"
BLOCKED = "BLOCKED"
READY_FOR_CONNECTION_REVIEW = "READY_FOR_CONNECTION_REVIEW"
MAX_SEQUENTIAL_ITEMS = 10
CLOCK_UNIT = "seconds"
_MARKER = re.compile(r"[A-Za-z0-9._-]{1,64}\Z")
_SETTING_NAME = re.compile(r"[A-Z0-9_]{1,128}\Z")
# No official wire-contract value is present in the checked-in approved sources.
OFFICIAL_WIRE_CONTRACT_VERSION: None = None


@dataclass(frozen=True, repr=False)
class RealTransportCapabilityManifest:
    contract_version: str
    official_wire_contract_version: str
    bounded_timeout: bool
    cancel_capability: bool
    no_retry: bool
    sequential: bool
    max_items: int
    redaction: bool
    kill_revoke_checkpoints: bool
    late_result_discard: bool

    def __repr__(self) -> str:
        return "<RealTransportCapabilityManifest>"


@dataclass(frozen=True, repr=False)
class ClockAdapterContract:
    monotonic: bool
    unit: str
    finite_range: bool
    nondecreasing: bool
    process_local_limitation_acknowledged: bool

    def __repr__(self) -> str:
        return "<ClockAdapterContract>"


@dataclass(frozen=True, repr=False)
class KillOperationsRunbookContract:
    default_disabled: bool
    revoke_procedure: bool
    rollback_procedure: bool
    audit_reason: bool
    reenable_requires_new_approval: bool
    automatic_unlock: bool

    def __repr__(self) -> str:
        return "<KillOperationsRunbookContract>"


@dataclass(frozen=True)
class CapabilityReceipt:
    contract_version: str
    status: str
    capability_not_ready: bool
    connection_review_allowed: bool
    activation_allowed: bool = False
    production_write_performed: bool = False
    deployment_allowed: bool = False
    route_enabled: bool = False
    reason_codes: tuple[str, ...] = ()


def _receipt(status: str, *reasons: str) -> CapabilityReceipt:
    return CapabilityReceipt(
        CONTRACT_VERSION, status, status != READY_FOR_CONNECTION_REVIEW,
        status == READY_FOR_CONNECTION_REVIEW, reason_codes=tuple(sorted(set(reasons))),
    )


def disabled_manifest() -> RealTransportCapabilityManifest:
    """Schema-only default; no official wire version or capability is asserted."""
    return RealTransportCapabilityManifest(
        CONTRACT_VERSION, UNCONFIRMED, False, False, False, False, 0, False, False, False,
    )


def disabled_clock_contract() -> ClockAdapterContract:
    return ClockAdapterContract(False, UNCONFIRMED, False, False, False)


def disabled_kill_runbook() -> KillOperationsRunbookContract:
    return KillOperationsRunbookContract(True, False, False, False, False, False)


def production_transport_adapter() -> None:
    """Fail-closed: no adapter or production connection exists."""
    return None


def evaluate_connection_preflight(
    *, manifest: Any, setting_names: Any, clock_contract: Any, kill_runbook: Any,
) -> CapabilityReceipt:
    """Validate schemas only; success never connects an adapter or enables production."""
    try:
        if not _settings_schema_valid(setting_names):
            return _receipt(BLOCKED, "SETTINGS_SCHEMA_INVALID")
        if not _manifest_valid(manifest):
            return _receipt(BLOCKED, "TRANSPORT_CAPABILITY_INVALID")
        if not _clock_contract_valid(clock_contract):
            return _receipt(BLOCKED, "CLOCK_CONTRACT_INVALID")
        if not _kill_runbook_valid(kill_runbook):
            return _receipt(BLOCKED, "KILL_RUNBOOK_INVALID")
        if OFFICIAL_WIRE_CONTRACT_VERSION is None:
            return _receipt(BLOCKED, "OFFICIAL_WIRE_CONTRACT_UNCONFIRMED")
        # Kept for a future separately approved official wire-contract addition.
        return _receipt(READY_FOR_CONNECTION_REVIEW, "CONNECTION_REVIEW_ONLY")
    except Exception:
        return _receipt(BLOCKED, "CAPABILITY_SCHEMA_INVALID")


def _settings_schema_valid(value: Any) -> bool:
    if type(value) not in (tuple, frozenset):
        return False
    if len(value) != len(REQUIRED_SETTING_NAMES):
        return False
    for name in value:
        if type(name) is not str or _SETTING_NAME.fullmatch(name) is None:
            return False
    return frozenset(value) == REQUIRED_SETTING_NAMES


def _manifest_valid(value: Any) -> bool:
    if type(value) is not RealTransportCapabilityManifest:
        return False
    if not _marker_valid(value.contract_version, CONTRACT_VERSION):
        return False
    if not _wire_marker_valid(value.official_wire_contract_version):
        return False
    return (
        value.bounded_timeout is True and value.cancel_capability is True
        and value.no_retry is True and value.sequential is True
        and type(value.max_items) is int and value.max_items == MAX_SEQUENTIAL_ITEMS
        and value.redaction is True and value.kill_revoke_checkpoints is True
        and value.late_result_discard is True
    )


def _clock_contract_valid(value: Any) -> bool:
    return type(value) is ClockAdapterContract and _marker_valid(value.unit, CLOCK_UNIT) and (
        value.monotonic is True and value.finite_range is True
        and value.nondecreasing is True and value.process_local_limitation_acknowledged is True
    )


def _kill_runbook_valid(value: Any) -> bool:
    return type(value) is KillOperationsRunbookContract and (
        value.default_disabled is True and value.revoke_procedure is True
        and value.rollback_procedure is True and value.audit_reason is True
        and value.reenable_requires_new_approval is True and value.automatic_unlock is False
    )


def _fake_clock_conforms_for_test(samples: Any) -> bool:
    """Pure test-only conformance check; it never calls a real clock."""
    if type(samples) not in (tuple, list) or not samples:
        return False
    previous = None
    for value in samples:
        if type(value) not in (int, float):
            return False
        try:
            if not math.isfinite(value) or (previous is not None and value < previous):
                return False
        except (OverflowError, TypeError, ValueError):
            return False
        previous = value
    return True


def _marker_valid(value: Any, expected: str) -> bool:
    return type(value) is str and _MARKER.fullmatch(value) is not None and value == expected


def _wire_marker_valid(value: Any) -> bool:
    if type(value) is not str or _MARKER.fullmatch(value) is None:
        return False
    if OFFICIAL_WIRE_CONTRACT_VERSION is None:
        return value == UNCONFIRMED
    return value == OFFICIAL_WIRE_CONTRACT_VERSION


__all__ = [
    "BLOCKED", "CLOCK_UNIT", "CONTRACT_VERSION", "CapabilityReceipt", "ClockAdapterContract",
    "KillOperationsRunbookContract", "MAX_SEQUENTIAL_ITEMS", "READY_FOR_CONNECTION_REVIEW",
    "RealTransportCapabilityManifest", "UNCONFIRMED", "disabled_clock_contract", "disabled_kill_runbook",
    "disabled_manifest", "evaluate_connection_preflight", "production_transport_adapter",
]
