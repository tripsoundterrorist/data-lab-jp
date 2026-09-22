"""Internal fake-lifecycle kill and deadline contract; production remains off."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


BLOCKED = "BLOCKED"
ACTIVE = "ACTIVE"


@dataclass
class _TestKillToken:
    _active: bool = True

    def revoke(self) -> None:
        self._active = False

    def __repr__(self) -> str:
        return "<KillToken>"


def _new_test_token() -> _TestKillToken:
    """Internal-only token issuer; no production issuer exists."""
    return _TestKillToken()


def _guarded_transport_for_test(
    token: Any, clock: Any, deadline: Any, transport: Any,
) -> Callable[[Any], Any]:
    """Bind one fake lifecycle to a token and trusted monotonic deadline."""
    if type(token) is not _TestKillToken or not callable(clock) or not callable(transport) or type(deadline) not in (int, float):
        raise ValueError("KILL_DEADLINE_INPUT_INVALID")

    def guarded(request: Any) -> Any:
        try:
            if token._active is not True or clock() >= deadline:
                return None
            response = transport(request)
            if token._active is not True or clock() >= deadline:
                return None
            return response
        except Exception:
            return None
    return guarded


def default_state() -> str:
    return BLOCKED
