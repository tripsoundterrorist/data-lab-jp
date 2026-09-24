"""Sanitized operator-attested status of the DMM follow-up inquiry."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from official_blocker_policy import LIFECYCLE_BLOCKER, SORT_BLOCKER
import revenue_mvp_official_response_batch_handoff as response_batch


VERSION = "0.2"
SUBMITTED_AWAITING_RESPONSE = "SUBMITTED_AWAITING_RESPONSE"
RESPONSE_RECEIVED_PARTIALLY_RESOLVED = "RESPONSE_RECEIVED_PARTIALLY_RESOLVED"
FAIL_CLOSED = "FAIL_CLOSED"
EVIDENCE_PATH = (
    Path(__file__).resolve().parents[1]
    / "runtime/evidence/revenue-mvp-official-response-20260916.json"
)
EXPECTED_UNANSWERED = {
    LIFECYCLE_BLOCKER: {"HISTORICAL_METADATA_RETENTION"},
    SORT_BLOCKER: {
        "OFFSET_MEANING",
        "POSITION_MEANING",
        "PUBLIC_POSITION_EXPRESSION",
        "UPDATE_BEHAVIOR",
    },
}
EXPECTED_NONRESOLVED_STATUSES = {
    LIFECYCLE_BLOCKER: {
        "HISTORICAL_METADATA_RETENTION": "PARTIALLY_RESOLVED",
    },
    SORT_BLOCKER: {
        "OFFSET_MEANING": "UNRESOLVED",
        "POSITION_MEANING": "UNRESOLVED",
        "PUBLIC_POSITION_EXPRESSION": "UNRESOLVED",
        "UPDATE_BEHAVIOR": "PARTIALLY_RESOLVED",
    },
}


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
    try:
        value = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
        reviewed = response_batch.handoff_batch(value)
        by_blocker = {
            entry["referenced_blocker"]: entry
            for entry in value
            if type(entry) is dict and "referenced_blocker" in entry
        }
        remaining_topics_match = (
            set(by_blocker) == {LIFECYCLE_BLOCKER, SORT_BLOCKER}
            and all(
                set(by_blocker[blocker].get("unanswered_questions", ()))
                == expected
                and {
                    question: by_blocker[blocker]
                    .get("answered_questions", {})
                    .get(question)
                    for question in expected
                }
                == EXPECTED_NONRESOLVED_STATUSES[blocker]
                for blocker, expected in EXPECTED_UNANSWERED.items()
            )
        )
        valid_partial = (
            reviewed.status == response_batch.RESPONSE_INCOMPLETE
            and reviewed.lifecycle_status == "PARTIALLY_RESOLVED"
            and reviewed.sort_status == "PARTIALLY_RESOLVED"
            and reviewed.lifecycle_resolved_question_count == 8
            and reviewed.sort_resolved_question_count == 4
            and reviewed.total_unresolved_question_count == 5
            and reviewed.total_contradictory_question_count == 0
            and reviewed.combined_gate_review_candidate is False
            and reviewed.gate_mutation_allowed is False
            and reviewed.production_activation_allowed is False
            and remaining_topics_match
        )
        if not valid_partial:
            raise ValueError("reviewed response evidence mismatch")
        return OfficialFollowupStatus(
            VERSION,
            RESPONSE_RECEIVED_PARTIALLY_RESOLVED,
            "2026-09-12",
            (LIFECYCLE_BLOCKER, SORT_BLOCKER),
            True,
            False,
            False,
            (
                "OPERATOR_CONFIRMED_SUBMISSION",
                "OFFICIAL_RESPONSE_RECEIVED",
                "OFFICIAL_SEMANTICS_PARTIALLY_RESOLVED",
            ),
        )
    except Exception:
        return OfficialFollowupStatus(
            VERSION,
            FAIL_CLOSED,
            "2026-09-12",
            (LIFECYCLE_BLOCKER, SORT_BLOCKER),
            False,
            False,
            False,
            ("REVIEWED_RESPONSE_EVIDENCE_INVALID",),
        )


def main() -> int:
    print(json.dumps(current_status().to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
