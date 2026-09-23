"""Sanitized status of the preconnection Q4/Q5 official inquiry."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any


VERSION = "0.1"
SUBMITTED_AWAITING_RESPONSE = "SUBMITTED_AWAITING_RESPONSE"
QUESTION_IDS = (
    "LIVE_SINGLE_REQUEST_PERMISSION",
    "USER_AGENT_REQUIREMENT",
)


@dataclass(frozen=True)
class PreconnectionFollowupStatus:
    version: str
    status: str
    submitted_at: str
    question_ids: tuple[str, ...]
    response_received: bool
    live_connection_allowed: bool
    gate_unlock_allowed: bool
    secrets_transmitted: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["question_ids"] = list(self.question_ids)
        value["reason_codes"] = list(self.reason_codes)
        return value


def current_status() -> PreconnectionFollowupStatus:
    """Return sanitized operator-attested state without message or account data."""
    return PreconnectionFollowupStatus(
        VERSION,
        SUBMITTED_AWAITING_RESPONSE,
        "2026-09-23T23:32:00+09:00",
        QUESTION_IDS,
        False,
        False,
        False,
        False,
        (
            "OPERATOR_CONFIRMED_SUBMISSION",
            "OFFICIAL_RESPONSE_PENDING",
            "LIVE_CONNECTION_REMAINS_BLOCKED",
        ),
    )


def main() -> int:
    print(json.dumps(current_status().to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
