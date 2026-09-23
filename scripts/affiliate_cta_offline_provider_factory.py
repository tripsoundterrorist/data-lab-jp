"""Test-only offline factory for the inert CTA observation-provider contract."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, Callable, Mapping
import affiliate_cta_approved_context as approved
import affiliate_cta_network_disabled_wire_adapter as synthetic_adapter
import affiliate_link_adapter
from affiliate_cta_kill_deadline_contract import _issue_lease_for_test

_HOSTS = frozenset({"al.dmm.co.jp", "al.fanza.co.jp"})


def _freeze(value: Any) -> Any:
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) in (list, tuple):
        return tuple(_freeze(item) for item in value)
    if type(value) in (str, int, float, bool, type(None)):
        return value
    raise ValueError("OFFLINE_RESPONSE_INVALID")


def _safe_match(response: Any, content_id: str) -> bool:
    if not isinstance(response, Mapping):
        return False
    result = response.get("result")
    if not isinstance(result, Mapping) or str(result.get("status")) != "200":
        return False
    items = result.get("items")
    if type(items) not in (list, tuple):
        return False
    matches = [item for item in items if isinstance(item, Mapping) and item.get("content_id") == content_id]
    if len(matches) != 1 or type(matches[0].get("affiliateURL")) is not str:
        return False
    return affiliate_link_adapter.validate_affiliate_target(
        matches[0]["affiliateURL"], allowed_hosts=_HOSTS,
    )


@dataclass(frozen=True, repr=False)
class _OfflineProvider:
    context: Any
    mapping: Mapping[str, str]
    fetcher: Callable[[str], Any]
    clock: Callable[[], Any]
    lease: Any
    generation: Any

    def __repr__(self):
        return "<OfflineProvider>"

    def valid(self):
        return approved._lease_valid(self.context, self)

    def revoke(self):
        self.lease.revoke()

    def observe(self, public_id: str) -> approved._InternalObservation | None:
        if not self.valid() or not approved._context_member(self.context, public_id):
            return None
        content_id = self.mapping.get(public_id)
        if type(content_id) is not str:
            return None
        try:
            if not self.valid():
                return None
            response = self.fetcher(content_id)
            if not self.valid():
                return None
            snapshot = _freeze(deepcopy(response))
            # Snapshot completion and entry to the provider clock are separate
            # trust boundaries, both sharing the same terminal lease state.
            if not self.valid():
                return None
            if not self.valid():
                return None
            checked_at = self.clock()
            if not self.valid():
                return None
        except Exception:
            self.revoke()
            return None
        if not isinstance(checked_at, datetime) or checked_at.tzinfo is None:
            self.revoke()
            return None
        if not _safe_match(snapshot, content_id):
            self.revoke()
            return None
        if not self.valid():
            return None
        observation = approved._InternalObservation(
            public_id, approved._context_digest(self.context), checked_at, content_id, snapshot,
            self.lease, self.generation, self.context, self,
        )
        return observation if approved._observation_bound(observation, self.context, self) else None

    def _consume_validated_synthetic_observation_for_test(
        self, public_id: Any, observation: Any,
    ) -> approved._InternalObservation | None:
        """Consume one adapter-issued synthetic observation without rebuilding a response."""
        if not self.valid() or not approved._context_member(self.context, public_id):
            return None
        content_id = self.mapping.get(public_id)
        if type(content_id) is not str:
            return None
        if not synthetic_adapter.consume_validated_synthetic_observation_for_offline_consumer(
            observation, content_id,
        ):
            return None
        try:
            if not self.valid():
                return None
            checked_at = self.clock()
            if not self.valid():
                return None
        except Exception:
            self.revoke()
            return None
        if not isinstance(checked_at, datetime) or checked_at.tzinfo is None:
            self.revoke()
            return None
        result = approved._InternalObservation(
            public_id, approved._context_digest(self.context), checked_at, content_id, observation,
            self.lease, self.generation, self.context, self,
        )
        return result if approved._observation_bound(result, self.context, self) else None

    def records(self, context: Any) -> tuple[approved._InternalPresentationRecord, ...] | None:
        if context is not self.context or not self.valid():
            return None
        values = []
        for public_id in sorted(context.public_ids):
            if not self.valid():
                return None
            observation = self.observe(public_id)
            if observation is None or not approved._observation_bound(observation, context, self):
                return None
            values.append(approved._InternalPresentationRecord(
                public_id, approved._context_digest(context), "Verified item", observation,
            ))
        result = tuple(values)
        return result if self.valid() else None


def _consume_validated_synthetic_for_test(
    provider: Any, public_id: Any, observation: Any,
) -> approved._InternalObservation | None:
    """Owner-controlled validation and consumption boundary for synthetic tests."""
    # Exact type is intentionally checked before any caller-owned attribute access.
    if type(provider) is not _OfflineProvider:
        return None
    try:
        context = provider.context
        if (
            not approved._lease_valid(context, provider)
            or not approved._context_member(context, public_id)
        ):
            return None
        result = provider._consume_validated_synthetic_observation_for_test(public_id, observation)
        if type(result) is not approved._InternalObservation:
            return None
        expected_content_id = provider.mapping.get(public_id)
        if (
            type(expected_content_id) is not str
            or result.public_id != public_id
            or result.resolved_content_id != expected_content_id
            or result.response is not observation
            or result.context is not context
            or result.provider is not provider
            or result.lease is not provider.lease
            or result.generation is not provider.generation
            or not approved._observation_bound(result, context, provider)
        ):
            return None
        return result
    except Exception:
        return None


def _build_offline_provider_for_test(
    context: Any, mapping: Any, fetcher: Any, clock: Any,
    *, monotonic_clock=lambda: 0, deadline=10,
) -> _OfflineProvider:
    """Internal test seam; production providers remain the inert defaults."""
    if (
        not approved._context_valid(context)
        or not isinstance(mapping, Mapping)
        or set(mapping) != context.public_ids
        or not callable(fetcher)
        or not callable(clock)
        or any(type(value) is not str or not value for value in mapping.values())
        or len(set(mapping.values())) != approved.EXACT_SELECTION_COUNT
    ):
        raise ValueError("OFFLINE_PROVIDER_INPUT_INVALID")
    # Each offline builder owns a fresh lease and a fresh context identity.
    lease = _issue_lease_for_test(monotonic_clock, deadline)
    bound_context = replace(context, lease=lease, generation=lease.generation)
    provider = _OfflineProvider(bound_context, MappingProxyType(dict(mapping)), fetcher,
                                clock, lease, lease.generation)
    if not lease.bind(bound_context, provider) or not provider.valid():
        raise ValueError("LIFECYCLE_BLOCKED")
    return provider
