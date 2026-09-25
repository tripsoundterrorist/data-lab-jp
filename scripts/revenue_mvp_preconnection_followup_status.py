"""Sanitized status of the preconnection Q4/Q5 official inquiry."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any


VERSION = "0.2"
SUBMITTED_AWAITING_RESPONSE = "SUBMITTED_AWAITING_RESPONSE"
RESPONSE_RECEIVED_REVIEW_REQUIRED = "RESPONSE_RECEIVED_REVIEW_REQUIRED"
QUESTION_IDS = (
    "LIVE_SINGLE_REQUEST_PERMISSION",
    "USER_AGENT_REQUIREMENT",
)


@dataclass(frozen=True)
class PreconnectionFollowupStatus:
    version: str
    status: str
    submitted_at: str
    responded_on: str | None
    question_ids: tuple[str, ...]
    live_single_request_permission: str
    user_agent_requirement: str
    response_received: bool
    live_connection_allowed: bool
    gate_unlock_allowed: bool
    secrets_transmitted: bool
    compliance_review_required: bool
    explicit_connection_approval_required: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["question_ids"] = list(self.question_ids)
        value["reason_codes"] = list(self.reason_codes)
        return value


def current_status() -> PreconnectionFollowupStatus:
    """Return sanitized operator-attested state without message or account data."""
    try:
        path = (Path(__file__).resolve().parents[1] / "runtime/evidence/"
                "revenue-mvp-preconnection-official-response-20260925.json")
        value = json.loads(path.read_text(encoding="utf-8"))
        states = value["question_states"]
        valid = (
            type(value) is dict
            and set(value) == {
                "evidence_version", "responded_on", "source_type",
                "source_authority", "question_states", "raw_message_stored",
                "live_connection_allowed", "gate_unlock_allowed",
                "compliance_review_required",
                "explicit_connection_approval_required",
            }
            and value["evidence_version"] == "0.1"
            and value["responded_on"] == "2026-09-25"
            and value["source_type"] == "DIRECT_SUPPORT_CONFIRMATION"
            and value["source_authority"] == "DMM_AFFILIATE_SUPPORT"
            and type(states) is dict
            and tuple(states) == QUESTION_IDS
            and states[QUESTION_IDS[0]] == "YES"
            and states[QUESTION_IDS[1]] == "NO"
            and value["raw_message_stored"] is False
            and value["live_connection_allowed"] is False
            and value["gate_unlock_allowed"] is False
            and value["compliance_review_required"] is True
            and value["explicit_connection_approval_required"] is True
        )
        if not valid:
            raise ValueError("official response evidence mismatch")
        return PreconnectionFollowupStatus(
            VERSION, RESPONSE_RECEIVED_REVIEW_REQUIRED,
            "2026-09-23T23:32:00+09:00", "2026-09-25", QUESTION_IDS,
            "YES", "NO", True, False, False, False, True, True,
            (
                "OPERATOR_CONFIRMED_SUBMISSION",
                "OFFICIAL_RESPONSE_RECEIVED",
                "Q4_SINGLE_REQUEST_PERMISSION_CONFIRMED",
                "Q5_USER_AGENT_REQUIREMENT_NOT_STATED",
                "SEPARATE_COMPLIANCE_REVIEW_REQUIRED",
                "LIVE_CONNECTION_REMAINS_BLOCKED",
            ),
        )
    except Exception:
        return PreconnectionFollowupStatus(
            VERSION, "FAIL_CLOSED", "2026-09-23T23:32:00+09:00", None,
            QUESTION_IDS, "UNSPECIFIED", "UNSPECIFIED", False, False, False,
            False, True, True, ("OFFICIAL_RESPONSE_EVIDENCE_INVALID",),
        )


def main() -> int:
    print(json.dumps(current_status().to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
