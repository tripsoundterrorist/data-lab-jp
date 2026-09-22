"""Offline-only bounded send contract; production adapters remain disabled."""
from __future__ import annotations

from dataclasses import dataclass
import math
from decimal import Decimal, ROUND_CEILING, localcontext
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
    trusted_started: Any = None
    trusted_finished: Any = None
    budget_ms: Any = None

    def __repr__(self) -> str:
        return "<BoundedSendOutcome>"


class _FakeBoundedExecutorForTest:
    """Deterministic no-thread/no-network executor used only by offline tests."""

    __slots__ = ("_mode", "_elapsed_ms")

    def __init__(self, mode: str = _COMPLETED, *, elapsed_ms: Any = None) -> None:
        if type(mode) is not str or mode not in _ALLOWED:
            raise ValueError("BOUNDED_EXECUTOR_MODE_INVALID")
        if elapsed_ms is not None and not _valid_elapsed_ms(elapsed_ms):
            raise ValueError("BOUNDED_EXECUTOR_ELAPSED_INVALID")
        self._mode = mode
        self._elapsed_ms = elapsed_ms

    def execute(
        self, request: Any, timeout_ms: Any, cancelled: Callable[[], bool], send: Callable[[Any], Any],
        pre_send: Callable[[], Any], post_send: Callable[[], Any],
    ) -> _SendOutcome:
        if not _valid_timeout_ms(timeout_ms) or not callable(cancelled) or not callable(send) or not callable(pre_send) or not callable(post_send):
            return _SendOutcome(_CANCELLED)
        try:
            if cancelled() or self._mode == _CANCELLED:
                return _SendOutcome(_CANCELLED)
            if self._mode == _TIMEOUT:
                return _SendOutcome(_TIMEOUT)
            prepared = pre_send()
            if type(prepared) is not tuple or len(prepared) != 2:
                return _SendOutcome(_CANCELLED)
            budget_ms, started = prepared
            # Never send with an earlier/larger budget after a fresh guard.
            if type(budget_ms) is not int or budget_ms != timeout_ms:
                return _SendOutcome(_CANCELLED)
            response = send(request)
            finished = post_send()
            if type(finished) is not tuple or len(finished) != 2:
                return _SendOutcome(_CANCELLED)
            elapsed_ms = self._elapsed_for_test(started, finished)
            if cancelled():
                return _SendOutcome(_CANCELLED)
            if self._mode == "LATE_RESULT":
                return _SendOutcome(_TIMEOUT)
            return _SendOutcome(_COMPLETED, response, elapsed_ms, started, finished[0], budget_ms)
        except Exception:
            return _SendOutcome(_CANCELLED)

    def _elapsed_for_test(self, started: Any, finished: Any) -> Any:
        if self._elapsed_ms is not None:
            return self._elapsed_ms
        if type(finished) is tuple:
            finished = finished[0]
        if type(started) not in (int, float) or type(finished) not in (int, float):
            return None
        return (finished - started) * 1_000

    def __repr__(self) -> str:
        return "<FakeBoundedExecutorForTest>"


def _send_for_test(
    *, executor: Any, request: Any, timeout_ms: Any, valid: Callable[[], bool],
    budget_snapshot: Callable[[], Any], revoke: Callable[[], None], transport: Callable[[Any], Any],
) -> Any:
    """Pre-send and post-send lease checkpoints; terminal failures never retry."""
    if (
        not _valid_timeout_ms(timeout_ms)
        or not isinstance(executor, _FakeBoundedExecutorForTest)
        or not callable(valid)
        or not callable(budget_snapshot)
        or not callable(revoke)
        or not callable(transport)
    ):
        return None
    try:
        if not valid() or (snapshot := budget_snapshot()) is None:
            return None
        effective_timeout_ms = _effective_timeout_ms(timeout_ms, _snapshot_budget(snapshot))
        if effective_timeout_ms is None:
            revoke()
            return None
        def pre_send():
            # This is the sole synchronous send marker guard. It rechecks the
            # identity-bound lease after every executor callback/clock boundary.
            if not valid() or (latest := budget_snapshot()) is None:
                return None
            current = _effective_timeout_ms(timeout_ms, _snapshot_budget(latest))
            if current != effective_timeout_ms:
                revoke()
                return None
            return current, latest[0]

        def post_send():
            if not valid() or (latest := budget_snapshot()) is None:
                return None
            return latest

        outcome = executor.execute(request, effective_timeout_ms, lambda: not valid(), transport, pre_send, post_send)
        if (
            type(outcome) is not _SendOutcome
            or outcome.status != _COMPLETED
            or not _valid_elapsed_ms(outcome.elapsed_ms)
            or outcome.budget_ms != effective_timeout_ms
            or not _trusted_elapsed_matches(outcome, effective_timeout_ms)
        ):
            revoke()
            return None
        # A response is untrusted until both the lease and its trusted clock are
        # checked after completion. Sub-millisecond/expired remaining time blocks.
        return outcome.response if valid() and budget_snapshot() is not None else None
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


def _snapshot_budget(value: Any) -> Any:
    if type(value) is not tuple or len(value) != 2:
        return None
    return value[1]


def _trusted_elapsed_matches(outcome: _SendOutcome, budget_ms: int) -> bool:
    if type(outcome.budget_ms) is not int or outcome.budget_ms != budget_ms:
        return False
    if type(outcome.trusted_started) not in (int, float) or type(outcome.trusted_finished) not in (int, float):
        return False
    trusted_elapsed = (outcome.trusted_finished - outcome.trusted_started) * 1_000
    trusted_us = _conservative_microseconds(trusted_elapsed)
    reported_us = _conservative_microseconds(outcome.elapsed_ms)
    budget_us = budget_ms * 1_000
    if trusted_us is None or reported_us is None or trusted_us >= budget_us or reported_us >= budget_us:
        return False
    # The shared clock and reported outcome must normalize to the exact same
    # conservative integer unit; there is no tolerance at the timeout boundary.
    return reported_us == trusted_us


def _conservative_microseconds(value_ms: Any) -> int | None:
    if not _valid_elapsed_ms(value_ms):
        return None
    try:
        with localcontext() as context:
            context.prec = 1_000
            value = Decimal(value_ms) if type(value_ms) is int else Decimal.from_float(value_ms)
            return int((value * 1_000).to_integral_value(rounding=ROUND_CEILING))
    except Exception:
        return None
