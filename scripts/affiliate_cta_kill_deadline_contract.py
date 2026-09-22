"""Internal fake-lifecycle kill and deadline contract; production remains off."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable


BLOCKED = "BLOCKED"
ACTIVE = "ACTIVE"


@dataclass
class _TestKillToken:
    _generation: object = None  # type: ignore[assignment]
    _terminal_generation: object | None = None

    def __post_init__(self) -> None:
        self._generation = object()

    def revoke(self) -> None:
        self._terminal_generation = self._generation

    def __repr__(self) -> str:
        return "<KillToken>"


def _new_test_token() -> _TestKillToken:
    """Internal-only token issuer; no production issuer exists."""
    return _TestKillToken()


def _valid_for_test(token: Any, clock: Any, deadline: Any, last: Any = None) -> tuple[bool, float | None]:
    if type(token) is not _TestKillToken or not callable(clock) or type(deadline) not in (int, float) or type(deadline) is bool or not math.isfinite(deadline):
        return False, None
    try:
        now = clock()
    except Exception:
        return False, None
    if type(now) not in (int, float) or type(now) is bool or not math.isfinite(now):
        return False, None
    if last is not None and now < last:
        return False, None
    return token._terminal_generation is not token._generation and now < deadline, now


def _guarded_transport_for_test(
    token: Any, clock: Any, deadline: Any, transport: Any,
) -> Callable[[Any], Any]:
    """Bind one fake lifecycle to a token and trusted monotonic deadline."""
    if type(token) is not _TestKillToken or not callable(clock) or not callable(transport):
        raise ValueError("KILL_DEADLINE_INPUT_INVALID")

    def guarded(request: Any) -> Any:
        try:
            valid, before = _valid_for_test(token, clock, deadline)
            if not valid:
                return None
            response = transport(request)
            valid, _after = _valid_for_test(token, clock, deadline, before)
            if not valid:
                return None
            return response
        except Exception:
            return None
    return guarded


def default_state() -> str:
    return BLOCKED
