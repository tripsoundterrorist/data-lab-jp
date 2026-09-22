"""Test-only offline factory for the inert CTA observation-provider contract."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

import affiliate_cta_approved_context as approved

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
    try:
        parsed = urlsplit(matches[0]["affiliateURL"])
        return (parsed.hostname or "").casefold().rstrip(".") in _HOSTS and parsed.port is None
    except ValueError:
        return False


@dataclass(frozen=True)
class _OfflineProvider:
    context: Any
    mapping: Mapping[str, str]
    fetcher: Callable[[str], Any]
    clock: Callable[[], Any]

    def observe(self, public_id: str) -> approved._InternalObservation | None:
        if not approved._context_member(self.context, public_id):
            return None
        content_id = self.mapping.get(public_id)
        if type(content_id) is not str:
            return None
        try:
            snapshot = _freeze(deepcopy(self.fetcher(content_id)))
            checked_at = self.clock()
        except Exception:
            return None
        if not isinstance(checked_at, datetime) or checked_at.tzinfo is None:
            return None
        if not _safe_match(snapshot, content_id):
            return None
        return approved._InternalObservation(
            public_id, approved._context_digest(self.context), checked_at, content_id, snapshot,
        )

    def records(self, context: Any) -> tuple[approved._InternalPresentationRecord, ...] | None:
        if context is not self.context or not approved._context_valid(context):
            return None
        values = []
        for public_id in sorted(context.public_ids):
            observation = self.observe(public_id)
            if observation is None:
                return None
            values.append(approved._InternalPresentationRecord(
                public_id, approved._context_digest(context), "Verified item", observation,
            ))
        return tuple(values)


def _build_offline_provider_for_test(
    context: Any, mapping: Any, fetcher: Any, clock: Any,
) -> _OfflineProvider:
    """Internal test seam; production providers remain the inert defaults."""
    if (
        not approved._context_valid(context)
        or type(mapping) is not dict
        or set(mapping) != context.public_ids
        or not callable(fetcher)
        or not callable(clock)
        or any(type(value) is not str or not value for value in mapping.values())
        or len(set(mapping.values())) != approved.EXACT_SELECTION_COUNT
    ):
        raise ValueError("OFFLINE_PROVIDER_INPUT_INVALID")
    return _OfflineProvider(context, MappingProxyType(dict(mapping)), fetcher, clock)
