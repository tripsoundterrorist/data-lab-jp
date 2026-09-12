"""Sanitized operator-attested status of the DMM follow-up inquiry."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

from official_blocker_policy import LIFECYCLE_BLOCKER, SORT_BLOCKER


VERSION = "0.1"
SUBMITTED_AWAITING_RESPONSE = "SUBMITTED_AWAITING_RESPONSE"


@dataclass(frozen=True)
class OfficialFollowupStatus:
    version: str
    status: str
    submitted_on: str
    covered_blockers: tuple[str, ...]
    response_received: bool
    official_semantics_resolved: bool
    gate_unlock_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["covered_blockers"] = list(self.covered_blockers)
        value["reason_codes"] = list(self.reason_codes)
        return value


def current_status() -> OfficialFollowupStatus:
    """Return only sanitized state; no message, account, or contact metadata."""
    return OfficialFollowupStatus(
        VERSION,
        SUBMITTED_AWAITING_RESPONSE,
        "2026-09-12",
        (LIFECYCLE_BLOCKER, SORT_BLOCKER),
        False,
        False,
        False,
        ("OPERATOR_CONFIRMED_SUBMISSION", "OFFICIAL_RESPONSE_PENDING"),
    )


def main() -> int:
    print(json.dumps(current_status().to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
