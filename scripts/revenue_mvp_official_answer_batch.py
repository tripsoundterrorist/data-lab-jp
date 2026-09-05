"""Safe batch intake for the twelve Revenue MVP official-answer topics."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping

import revenue_mvp_official_answer_matrix as matrix


VERSION = "0.1"
ACCEPTED = "ACCEPTED_FOR_MANUAL_REVIEW"
FAIL_CLOSED = "FAIL_CLOSED"
SOURCE_TYPES = frozenset({"DIRECT_SUPPORT_CONFIRMATION", "OFFICIAL_DOCUMENTATION"})
AUTHORITIES = frozenset({"DMM_AFFILIATE_SUPPORT", "DMM_OFFICIAL_DOCUMENTATION"})
TOP_LEVEL_KEYS = frozenset({
    "batch_version", "source_type", "source_authority", "received_at", "topics",
})
TOPIC_KEYS = frozenset({"status", "conditions_verified", "evidence_confirmed"})
UNSAFE_KEY = re.compile(
    r"(?i)(?:raw|body|sender|email|url|credential|secret|token|api_id|affiliate_id|path|exception|traceback)"
)


@dataclass(frozen=True)
class OfficialAnswerBatchResult:
    version: str
    intake_status: str
    matrix_status: str
    core_publication_candidate: bool
    sns_operation_candidate: bool
    gate_unlock_allowed: bool
    manual_review_required: bool
    accepted_topic_count: int
    blocking_topic_ids: tuple[str, ...]
    conditional_topic_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    normalized_entries: Mapping[str, matrix.AnswerDecision]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "intake_status": self.intake_status,
            "matrix_status": self.matrix_status,
            "core_publication_candidate": self.core_publication_candidate,
            "sns_operation_candidate": self.sns_operation_candidate,
            "gate_unlock_allowed": self.gate_unlock_allowed,
            "manual_review_required": self.manual_review_required,
            "accepted_topic_count": self.accepted_topic_count,
            "blocking_topic_ids": list(self.blocking_topic_ids),
            "conditional_topic_ids": list(self.conditional_topic_ids),
            "reason_codes": list(self.reason_codes),
        }


def _timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized).tzinfo is not None
    except ValueError:
        return False


def _failed(*reasons: str) -> OfficialAnswerBatchResult:
    return OfficialAnswerBatchResult(
        VERSION, FAIL_CLOSED, FAIL_CLOSED, False, False, False, True, 0,
        matrix.TOPIC_IDS, (), tuple(sorted(set(reasons))), MappingProxyType({}),
    )


def validate_batch(value: Any) -> OfficialAnswerBatchResult:
    """Validate sanitized decisions and delegate publication semantics to Matrix."""

    try:
        if not isinstance(value, Mapping):
            return _failed("MALFORMED_BATCH")
        keys = set(value)
        if any(not isinstance(key, str) or UNSAFE_KEY.search(key) for key in keys):
            return _failed("UNSAFE_INPUT")
        if keys != TOP_LEVEL_KEYS:
            return _failed("INVALID_BATCH_KEYS")
        if value["batch_version"] != VERSION:
            return _failed("UNKNOWN_BATCH_VERSION")
        if value["source_type"] not in SOURCE_TYPES:
            return _failed("UNVERIFIED_SOURCE_TYPE")
        if value["source_authority"] not in AUTHORITIES:
            return _failed("UNVERIFIED_SOURCE_AUTHORITY")
        if not _timestamp(value["received_at"]):
            return _failed("INVALID_RECEIVED_AT")
        topics = value["topics"]
        if not isinstance(topics, Mapping):
            return _failed("MALFORMED_TOPICS")
        if any(not isinstance(topic, str) or topic not in matrix.TOPIC_IDS for topic in topics):
            return _failed("UNKNOWN_TOPIC")

        entries: dict[str, matrix.AnswerDecision] = {}
        for topic, decision in topics.items():
            if not isinstance(decision, Mapping) or set(decision) != TOPIC_KEYS:
                return _failed("INVALID_TOPIC_DECISION")
            if any(
                not isinstance(key, str) or UNSAFE_KEY.search(key)
                for key in decision
            ):
                return _failed("UNSAFE_INPUT")
            status = decision["status"]
            conditions = decision["conditions_verified"]
            evidence = decision["evidence_confirmed"]
            if status not in matrix.STATUSES:
                return _failed("INVALID_TOPIC_STATUS")
            if not isinstance(conditions, bool) or not isinstance(evidence, bool):
                return _failed("INVALID_BOOLEAN_STATE")
            if status in {matrix.ALLOWED, matrix.CONDITIONALLY_ALLOWED} and not evidence:
                return _failed("OFFICIAL_EVIDENCE_REQUIRED")
            if status != matrix.CONDITIONALLY_ALLOWED and conditions:
                return _failed("CONTRADICTORY_CONDITION_STATE")
            if status in {matrix.UNKNOWN, matrix.FOLLOW_UP_REQUIRED} and evidence:
                return _failed("CONTRADICTORY_EVIDENCE_STATE")
            entries[topic] = matrix.AnswerDecision(status, conditions)

        assessed = matrix.assess_answer_matrix(entries)
        return OfficialAnswerBatchResult(
            VERSION, ACCEPTED, assessed.status,
            assessed.core_publication_candidate, assessed.sns_operation_candidate,
            False, True, len(entries), assessed.blocking_topic_ids,
            assessed.conditional_topic_ids,
            tuple(sorted(set(assessed.reason_codes) | {"SEPARATE_COMMIT_REVIEW_REQUIRED"})),
            MappingProxyType(dict(entries)),
        )
    except Exception:
        return _failed("BATCH_INTAKE_INTERNAL_ERROR")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a sanitized DMM/FANZA official-answer batch."
    )
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        value = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        result = _failed("BATCH_INPUT_UNAVAILABLE")
    else:
        result = validate_batch(value)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.intake_status == ACCEPTED else 2


if __name__ == "__main__":
    raise SystemExit(main())
