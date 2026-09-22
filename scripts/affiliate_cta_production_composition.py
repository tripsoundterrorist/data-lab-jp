"""Disabled production-provider composition root with an offline review seam."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import affiliate_cta_approved_context as approved
import affiliate_cta_bounded_send_contract as bounded
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
    *, monotonic_clock=lambda: 0, deadline=10, executor=None,
    timeout_ms=bounded.DEFAULT_TIMEOUT_MS,
) -> _OfflineComposition:
    """Internal offline-review seam; it cannot enable production transport."""
    if not approved._context_valid(context) or not callable(transport):
        raise ValueError("OFFLINE_COMPOSITION_INPUT_INVALID")

    chosen_executor = executor if executor is not None else bounded._FakeBoundedExecutorForTest()
    if not isinstance(chosen_executor, bounded._FakeBoundedExecutorForTest):
        raise ValueError("OFFLINE_EXECUTOR_CLOCK_INVALID")
    provider_holder = {}

    def fetch(content_id: str) -> Any:
        provider = provider_holder.get("provider")
        if provider is None:
            return None
        return bounded._send_for_test(
            executor=chosen_executor, request=_OpaqueProviderRequest(content_id), timeout_ms=timeout_ms,
            valid=provider.valid, budget_snapshot=provider.lease.send_budget,
            revoke=provider.revoke, transport=transport,
        )

    provider = factory._build_offline_provider_for_test(
        context, mapping, fetch, clock, monotonic_clock=monotonic_clock, deadline=deadline,
    )
    provider_holder["provider"] = provider
    return _OfflineComposition(provider, provider.context, provider.lease, provider.generation)


def _valid_lifecycle(value: Any) -> bool:
    try:
        return type(value) is _OfflineComposition and value.valid()
    except Exception:
        return False
