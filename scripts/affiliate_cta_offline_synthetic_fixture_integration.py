"""Offline-only handoff from a strict synthetic fixture to an opaque harness.

This module is deliberately not a provider, route, transport, or serializer.
It accepts only the adapter's already-validated opaque observation and exposes
only fixed status facts for regression tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import affiliate_cta_network_disabled_wire_adapter as adapter


ACCEPTED = "SYNTHETIC_OBSERVATION_ACCEPTED"
REJECTED = "SYNTHETIC_OBSERVATION_REJECTED"
FAIL_CLOSED = "SYNTHETIC_OBSERVATION_FAIL_CLOSED"


@dataclass(frozen=True, repr=False)
class OfflineSyntheticIntegrationReceipt:
    status: str
    adapter_validated: bool
    harness_accepted: bool
    production_activation_allowed: bool = False
    serialization_allowed: bool = False

    def __repr__(self) -> str:
        return "<OfflineSyntheticIntegrationReceipt>"


class _ValidatedObservationHarness:
    """Existing-value-free endpoint for one adapter-owned opaque observation."""

    __slots__ = ()

    def accept(self, observation: Any) -> bool:
        return type(observation) is adapter.ValidatedSyntheticFixtureObservation


_HARNESS = _ValidatedObservationHarness()


def production_integration() -> None:
    """Production activation is intentionally unavailable."""
    return None


def _run_synthetic_fixture_integration_for_test(
    *, payload: Any, requested_content_id: Any,
) -> OfflineSyntheticIntegrationReceipt:
    """Run exactly one validation and opaque handoff, entirely in memory."""
    try:
        observation = adapter.validate_synthetic_fixture_for_offline_harness(
            payload, requested_content_id,
        )
        if type(observation) is not adapter.ValidatedSyntheticFixtureObservation:
            return OfflineSyntheticIntegrationReceipt(REJECTED, False, False)
        if _HARNESS.accept(observation) is not True:
            return OfflineSyntheticIntegrationReceipt(FAIL_CLOSED, True, False)
        return OfflineSyntheticIntegrationReceipt(ACCEPTED, True, True)
    except Exception:
        return OfflineSyntheticIntegrationReceipt(FAIL_CLOSED, False, False)


__all__ = [
    "ACCEPTED", "FAIL_CLOSED", "OfflineSyntheticIntegrationReceipt", "REJECTED",
    "production_integration",
]
