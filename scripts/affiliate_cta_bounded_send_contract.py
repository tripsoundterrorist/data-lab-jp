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
    try:
        return (
            type(value) in (int, float)
            and not isinstance(value, bool)
            and math.isfinite(value)
            and MIN_TIMEOUT_MS <= value <= MAX_TIMEOUT_MS
        )
    except (OverflowError, TypeError, ValueError):
        return False


@dataclass(frozen=True, repr=False)
class _SendOutcome:
    status: str
    response: Any = None
    elapsed_ms: Any = 0

    def __repr__(self) -> str:
        return "<BoundedSendOutcome>"


class _FakeBoundedExecutorForTest:
    """Deterministic no-thread/no-network executor used only by offline tests."""

    __slots__ = ("_mode", "_elapsed_ms", "_monotonic_clock")

    def __init__(self, mode: str = _COMPLETED, *, elapsed_ms: Any = None,
                 monotonic_clock: Any = None) -> None:
        if type(mode) is not str or mode not in _ALLOWED:
            raise ValueError("BOUNDED_EXECUTOR_MODE_INVALID")
        if elapsed_ms is not None and not _valid_elapsed_ms(elapsed_ms):
            raise ValueError("BOUNDED_EXECUTOR_ELAPSED_INVALID")
        if monotonic_clock is not None and not callable(monotonic_clock):
            raise ValueError("BOUNDED_EXECUTOR_CLOCK_INVALID")
        self._mode = mode
        self._elapsed_ms = elapsed_ms
        self._monotonic_clock = monotonic_clock

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
            started = self._now_for_test()
            response = send(request)
            elapsed_ms = self._elapsed_for_test(started)
            if cancelled():
                return _SendOutcome(_CANCELLED)
            if self._mode == "LATE_RESULT":
                return _SendOutcome(_TIMEOUT)
            return _SendOutcome(_COMPLETED, response, elapsed_ms)
        except Exception:
            return _SendOutcome(_CANCELLED)

    def _now_for_test(self) -> Any:
        return None if self._monotonic_clock is None else self._monotonic_clock()

    def _elapsed_for_test(self, started: Any) -> Any:
        if self._elapsed_ms is not None:
            return self._elapsed_ms
        if self._monotonic_clock is None:
            return 0
        finished = self._monotonic_clock()
        if type(started) not in (int, float) or type(finished) not in (int, float):
            return None
        return (finished - started) * 1_000

    def __repr__(self) -> str:
        return "<FakeBoundedExecutorForTest>"


def _send_for_test(
    *, executor: Any, request: Any, timeout_ms: Any, valid: Callable[[], bool],
    remaining_ms: Callable[[], Any], revoke: Callable[[], None], transport: Callable[[Any], Any],
) -> Any:
    """Pre-send and post-send lease checkpoints; terminal failures never retry."""
    if (
        not _valid_timeout_ms(timeout_ms)
        or not isinstance(executor, _FakeBoundedExecutorForTest)
        or not callable(valid)
        or not callable(remaining_ms)
        or not callable(revoke)
        or not callable(transport)
    ):
        return None
    try:
        # Lease time is seconds; remaining_ms is floor-converted internally so
        # this finite integer budget cannot exceed the active lease.
        if not valid() or (remaining := remaining_ms()) is None:
            return None
        effective_timeout_ms = _effective_timeout_ms(timeout_ms, remaining)
        if effective_timeout_ms is None:
            revoke()
            return None
        outcome = executor.execute(request, effective_timeout_ms, lambda: not valid(), transport)
        if (
            type(outcome) is not _SendOutcome
            or outcome.status != _COMPLETED
            or not _valid_elapsed_ms(outcome.elapsed_ms)
            or outcome.elapsed_ms >= effective_timeout_ms
        ):
            revoke()
            return None
        # A response is untrusted until both the lease and its trusted clock are
        # checked after completion. Sub-millisecond/expired remaining time blocks.
        return outcome.response if valid() and remaining_ms() is not None else None
    except Exception:
        revoke()
        return None


def _valid_elapsed_ms(value: Any) -> bool:
    try:
        return type(value) in (int, float) and not isinstance(value, bool) and math.isfinite(value) and value >= 0
    except (OverflowError, TypeError, ValueError):
        return False


def _effective_timeout_ms(configured_timeout_ms: Any, remaining_ms: Any) -> int | None:
    if not _valid_timeout_ms(configured_timeout_ms) or type(remaining_ms) is not int:
        return None
    value = math.floor(min(configured_timeout_ms, remaining_ms, MAX_TIMEOUT_MS))
    return value if MIN_TIMEOUT_MS <= value <= MAX_TIMEOUT_MS else None
