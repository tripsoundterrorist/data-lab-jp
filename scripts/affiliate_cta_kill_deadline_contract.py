"""Internal lease for offline review. No production issuer or network code.

State lives in a closure: revoke, expiry, invalid time and clock regression are
terminal for the entire lifecycle. Python process/code mutation is not an
isolation boundary. A transport that never returns is not interrupted here.
"""
from __future__ import annotations

import math
from decimal import Decimal, ROUND_FLOOR
from typing import Any

BLOCKED = "BLOCKED"
_MILLISECONDS_PER_SECOND = 1_000
_MIN_SEND_BUDGET_MS = 1


def _finite(value: Any) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


class _LifecycleLease:
    __slots__ = ("__check", "__remaining_ms", "__send_budget", "__revoke", "__bind", "__matches", "__generation")

    def __new__(cls):
        raise TypeError("LEASE_INTERNAL_ISSUER_REQUIRED")

    def __setattr__(self, name, value):
        raise AttributeError("LEASE_IMMUTABLE")

    def __repr__(self):
        return "<LifecycleLease>"

    @property
    def generation(self):
        return self.__generation

    def valid(self) -> bool:
        return self.__check()

    def remaining_ms(self) -> int | None:
        """Internal send budget, rounded down so it never exceeds the lease."""
        return self.__remaining_ms()

    def send_budget(self) -> tuple[Any, int] | None:
        """Internal trusted monotonic timestamp and whole-millisecond budget."""
        return self.__send_budget()

    def revoke(self) -> None:
        self.__revoke()

    def bind(self, context, provider) -> bool:
        return self.__bind(context, provider)

    def matches(self, context, provider, generation) -> bool:
        return self.__matches(context, provider, generation)


def _issue_lease_for_test(monotonic_clock: Any, deadline: Any) -> _LifecycleLease:
    """Called by offline builders only; deadline is exclusive (now < deadline)."""
    lease = object.__new__(_LifecycleLease)
    generation = object()
    terminal = not callable(monotonic_clock) or not _finite(deadline)
    checking = False
    last = None
    bound = None

    def revoke():
        nonlocal terminal
        terminal = True

    def check():
        nonlocal terminal, last, checking
        if terminal or checking:
            revoke()
            return False
        checking = True
        try:
            now = monotonic_clock()
            if terminal or not _finite(now) or (last is not None and now < last) or now >= deadline:
                revoke()
                return False
            last = now
            return True
        except Exception:
            revoke()
            return False
        finally:
            checking = False

    def send_budget():
        nonlocal terminal, last, checking
        if terminal or checking:
            revoke()
            return None
        checking = True
        try:
            now = monotonic_clock()
            if terminal or not _finite(now) or (last is not None and now < last) or now >= deadline:
                revoke()
                return None
            # The clock/deadline unit is seconds. Decimal.from_float preserves
            # the actual binary-float value before floor conversion, so a budget
            # never rounds above the represented lease duration.
            left = _decimal_seconds(deadline) - _decimal_seconds(now)
            value = int((left * _MILLISECONDS_PER_SECOND).to_integral_value(rounding=ROUND_FLOOR))
            if value < _MIN_SEND_BUDGET_MS:
                revoke()
                return None
            last = now
            return now, value
        except Exception:
            revoke()
            return None
        finally:
            checking = False

    def remaining_ms():
        value = send_budget()
        return None if value is None else value[1]

    def bind(context, provider):
        nonlocal bound
        if bound is not None or not check():
            return False
        bound = (context, provider)
        return True

    def matches(context, provider, candidate_generation):
        return (bound is not None and context is bound[0] and provider is bound[1]
                and candidate_generation is generation and check())

    for name, value in (("check", check), ("remaining_ms", remaining_ms), ("send_budget", send_budget), ("revoke", revoke), ("bind", bind),
                        ("matches", matches), ("generation", generation)):
        object.__setattr__(lease, "_LifecycleLease__" + name, value)
    return lease


def default_state() -> str:
    return BLOCKED


def _decimal_seconds(value: Any) -> Decimal:
    if type(value) is int:
        return Decimal(value)
    if type(value) is float:
        return Decimal.from_float(value)
    raise ValueError("LEASE_CLOCK_INVALID")
