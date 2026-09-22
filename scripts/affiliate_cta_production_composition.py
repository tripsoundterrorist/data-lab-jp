"""Disabled production-provider composition root with an offline review seam."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import affiliate_cta_approved_context as approved
import affiliate_cta_offline_provider_factory as factory


KILL_SWITCH_DISABLED = True


class _OpaqueProviderRequest:
    __slots__ = ("_content_id",)

    def __init__(self, content_id: str) -> None:
        self._content_id = content_id

    def __repr__(self) -> str:
        return "<OpaqueProviderRequest>"


@dataclass(frozen=True, repr=False)
class _OfflineComposition:
    provider: Any
    context: Any
    lease: Any
    generation: Any

    def __repr__(self):
        return "<OfflineComposition>"

    def valid(self):
        try:
            return (self.context.lease is self.lease
                    and self.context.generation is self.generation
                    and approved._lease_valid(self.context, self.provider))
        except Exception:
            return False

    def revoke(self):
        self.lease.revoke()

    def observe(self, public_id: str) -> Any:
        if not self.valid():
            return None
        value = self.provider.observe(public_id)
        return value if self.valid() else None

    def records(self, context: Any) -> Any:
        if context is not self.context or not self.valid():
            return None
        value = self.provider.records(context)
        return value if self.valid() else None


def production_provider() -> None:
    """Kill switch: no network transport or protected configuration is present."""
    return None


def _build_offline_composition_for_test(
    context: Any, mapping: Any, transport: Any, clock: Any,
    *, monotonic_clock=lambda: 0, deadline=10,
) -> _OfflineComposition:
    """Internal offline-review seam; it cannot enable production transport."""
    if not approved._context_valid(context) or not callable(transport):
        raise ValueError("OFFLINE_COMPOSITION_INPUT_INVALID")

    def fetch(content_id: str) -> Any:
        return transport(_OpaqueProviderRequest(content_id))

    provider = factory._build_offline_provider_for_test(
        context, mapping, fetch, clock, monotonic_clock=monotonic_clock, deadline=deadline,
    )
    return _OfflineComposition(provider, provider.context, provider.lease, provider.generation)


def _valid_lifecycle(value: Any) -> bool:
    try:
        return type(value) is _OfflineComposition and value.valid()
    except Exception:
        return False
