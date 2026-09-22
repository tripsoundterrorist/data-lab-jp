"""Offline-only bounded send contract; production adapters remain disabled."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable


MIN_TIMEOUT_MS = 1
MAX_TIMEOUT_MS = 5_000
DEFAULT_TIMEOUT_MS = 1_000
_COMPLETED = "COMPLETED"
_TIMEOUT = "TIMEOUT"
_CANCELLED = "CANCELLED"
_ALLOWED = frozenset({_COMPLETED, _TIMEOUT, _CANCELLED, "LATE_RESULT"})


class ProductionMonotonicClock:
    """Declared production interface with no enabled clock implementation."""

    def now(self) -> None:
        return None

    def __repr__(self) -> str:
        return "<ProductionMonotonicClock disabled>"


class ProductionBoundedExecutor:
    """Declared production interface with no enabled send capability."""

    def execute(self, _request: Any, _timeout_ms: Any, _cancelled: Any, _send: Any) -> None:
        return None

    def __repr__(self) -> str:
        return "<ProductionBoundedExecutor disabled>"


def production_monotonic_clock() -> None:
    return None


def production_bounded_executor() -> None:
    return None


def _valid_timeout_ms(value: Any) -> bool:
    return (
        type(value) in (int, float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and MIN_TIMEOUT_MS <= value <= MAX_TIMEOUT_MS
    )


@dataclass(frozen=True, repr=False)
class _SendOutcome:
    status: str
    response: Any = None

    def __repr__(self) -> str:
        return "<BoundedSendOutcome>"


class _FakeBoundedExecutorForTest:
    """Deterministic no-thread/no-network executor used only by offline tests."""

    __slots__ = ("_mode",)

    def __init__(self, mode: str = _COMPLETED) -> None:
        if type(mode) is not str or mode not in _ALLOWED:
            raise ValueError("BOUNDED_EXECUTOR_MODE_INVALID")
        self._mode = mode

    def execute(
        self, request: Any, timeout_ms: Any, cancelled: Callable[[], bool], send: Callable[[Any], Any],
    ) -> _SendOutcome:
        if not _valid_timeout_ms(timeout_ms) or not callable(cancelled) or not callable(send):
            return _SendOutcome(_CANCELLED)
        try:
            if cancelled() or self._mode == _CANCELLED:
                return _SendOutcome(_CANCELLED)
            if self._mode == _TIMEOUT:
                return _SendOutcome(_TIMEOUT)
            response = send(request)
            if cancelled():
                return _SendOutcome(_CANCELLED)
            if self._mode == "LATE_RESULT":
                return _SendOutcome(_TIMEOUT)
            return _SendOutcome(_COMPLETED, response)
        except Exception:
            return _SendOutcome(_CANCELLED)

    def __repr__(self) -> str:
        return "<FakeBoundedExecutorForTest>"


def _send_for_test(
    *, executor: Any, request: Any, timeout_ms: Any, valid: Callable[[], bool],
    revoke: Callable[[], None], transport: Callable[[Any], Any],
) -> Any:
    """Pre-send and post-send lease checkpoints; terminal failures never retry."""
    if (
        not _valid_timeout_ms(timeout_ms)
        or not isinstance(executor, _FakeBoundedExecutorForTest)
        or not callable(valid)
        or not callable(revoke)
        or not callable(transport)
    ):
        return None
    try:
        if not valid():
            return None
        outcome = executor.execute(request, timeout_ms, lambda: not valid(), transport)
        if type(outcome) is not _SendOutcome or outcome.status != _COMPLETED:
            revoke()
            return None
        # A response is untrusted until the same active lease is checked again.
        return outcome.response if valid() else None
    except Exception:
        revoke()
        return None
