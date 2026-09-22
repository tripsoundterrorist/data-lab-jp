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


@dataclass(frozen=True)
class _OfflineComposition:
    provider: Any

    def observe(self, public_id: str) -> Any:
        return self.provider.observe(public_id)

    def records(self, context: Any) -> Any:
        return self.provider.records(context)


def production_provider() -> None:
    """Kill switch: no network transport or protected configuration is present."""
    return None


def _build_offline_composition_for_test(
    context: Any, mapping: Any, transport: Any, clock: Any,
) -> _OfflineComposition:
    """Internal offline-review seam; it cannot enable production transport."""
    if not approved._context_valid(context) or not callable(transport):
        raise ValueError("OFFLINE_COMPOSITION_INPUT_INVALID")

    def fetch(content_id: str) -> Any:
        return transport(_OpaqueProviderRequest(content_id))

    return _OfflineComposition(
        factory._build_offline_provider_for_test(context, mapping, fetch, clock)
    )
