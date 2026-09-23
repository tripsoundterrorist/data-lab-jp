"""Offline-only handoff from a strict synthetic fixture to the test provider.

This module is deliberately not a provider, route, transport, or serializer.
It accepts only the adapter's already-validated opaque observation and passes
it to the existing offline provider's owner-controlled test seam. It exposes
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


def production_integration() -> None:
    """Production activation is intentionally unavailable."""
    return None


def _run_synthetic_fixture_integration_for_test(
    *, payload: Any, requested_content_id: Any, provider: Any, public_id: Any,
) -> OfflineSyntheticIntegrationReceipt:
    """Run exactly one validation and one provider-owned opaque consumption."""
    try:
        observation = adapter.validate_synthetic_fixture_for_offline_harness(
            payload, requested_content_id,
        )
    except Exception:
        return OfflineSyntheticIntegrationReceipt(FAIL_CLOSED, False, False)
    if type(observation) is not adapter.ValidatedSyntheticFixtureObservation:
        return OfflineSyntheticIntegrationReceipt(REJECTED, False, False)
    try:
        consumed = provider._consume_validated_synthetic_observation_for_test(public_id, observation)
        if consumed is None:
            return OfflineSyntheticIntegrationReceipt(FAIL_CLOSED, True, False)
        return OfflineSyntheticIntegrationReceipt(ACCEPTED, True, True)
    except Exception:
        return OfflineSyntheticIntegrationReceipt(FAIL_CLOSED, True, False)


__all__ = [
    "ACCEPTED", "FAIL_CLOSED", "OfflineSyntheticIntegrationReceipt", "REJECTED",
    "production_integration",
]
