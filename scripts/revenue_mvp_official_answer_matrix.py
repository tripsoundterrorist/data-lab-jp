"""Sanitized Issue #66 answer matrix; never mutates publication gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any, Mapping


MATRIX_VERSION = "0.1"
ALLOWED = "ALLOWED"
CONDITIONALLY_ALLOWED = "CONDITIONALLY_ALLOWED"
UNKNOWN = "UNKNOWN"
FOLLOW_UP_REQUIRED = "FOLLOW_UP_REQUIRED"
STATUSES = frozenset({ALLOWED, CONDITIONALLY_ALLOWED, UNKNOWN, FOLLOW_UP_REQUIRED})

TOPIC_IDS = (
    "API_HISTORY_DISPLAY",
    "RETENTION_UPDATE_DELETION",
    "DERIVED_RANKINGS_AND_METRICS",
    "OFFICIAL_RANKING_CONFUSION",
    "API_IMAGE_USE",
    "DISCONTINUED_ITEM_HANDLING",
    "SNS_TO_SITE_TO_FANZA_FUNNEL",
    "SNS_ACCOUNT_REGISTRATION",
    "SNS_PRODUCT_MEDIA_USE",
    "AUTOMATED_FACT_POSTING",
    "PR_AD_AFFILIATE_DISCLOSURE",
    "PRODUCTION_DOMAIN_CHANGE",
)
CORE_TOPIC_IDS = frozenset({
    "API_HISTORY_DISPLAY", "RETENTION_UPDATE_DELETION",
    "DERIVED_RANKINGS_AND_METRICS", "OFFICIAL_RANKING_CONFUSION",
    "API_IMAGE_USE", "DISCONTINUED_ITEM_HANDLING",
    "PR_AD_AFFILIATE_DISCLOSURE", "PRODUCTION_DOMAIN_CHANGE",
})
SNS_TOPIC_IDS = frozenset(set(TOPIC_IDS) - CORE_TOPIC_IDS)


@dataclass(frozen=True)
class AnswerDecision:
    status: str
    conditions_verified: bool = False


@dataclass(frozen=True)
class AnswerMatrixResult:
    matrix_version: str
    status: str
    core_publication_candidate: bool
    sns_operation_candidate: bool
    gate_unlock_allowed: bool
    manual_review_required: bool
    counts: Mapping[str, int]
    blocking_topic_ids: tuple[str, ...]
    conditional_topic_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["counts"] = dict(self.counts)
        value["blocking_topic_ids"] = list(self.blocking_topic_ids)
        value["conditional_topic_ids"] = list(self.conditional_topic_ids)
        value["reason_codes"] = list(self.reason_codes)
        return value


def assess_answer_matrix(entries: Any) -> AnswerMatrixResult:
    reasons: set[str] = set()
    if not isinstance(entries, Mapping) or any(not isinstance(key, str) for key in entries):
        reasons.add("MALFORMED_INPUT")
        entries = {}
    if set(entries) - set(TOPIC_IDS):
        reasons.add("UNKNOWN_TOPIC")

    normalized: dict[str, AnswerDecision] = {}
    for topic in TOPIC_IDS:
        value = entries.get(topic, AnswerDecision(UNKNOWN))
        if not isinstance(value, AnswerDecision) or value.status not in STATUSES:
            reasons.add("INVALID_DECISION")
            normalized[topic] = AnswerDecision(UNKNOWN)
            continue
        if not isinstance(value.conditions_verified, bool):
            reasons.add("INVALID_CONDITION_STATE")
            normalized[topic] = AnswerDecision(UNKNOWN)
            continue
        if value.status != CONDITIONALLY_ALLOWED and value.conditions_verified:
            reasons.add("CONTRADICTORY_CONDITION_STATE")
            normalized[topic] = AnswerDecision(FOLLOW_UP_REQUIRED)
            continue
        normalized[topic] = value

    def resolved(topic: str) -> bool:
        decision = normalized[topic]
        return decision.status == ALLOWED or (
            decision.status == CONDITIONALLY_ALLOWED and decision.conditions_verified
        )

    blocking = tuple(topic for topic in TOPIC_IDS if not resolved(topic))
    conditional = tuple(
        topic for topic in TOPIC_IDS
        if normalized[topic].status == CONDITIONALLY_ALLOWED
    )
    core = not reasons and all(resolved(topic) for topic in CORE_TOPIC_IDS)
    sns = not reasons and all(resolved(topic) for topic in SNS_TOPIC_IDS)
    if blocking:
        reasons.add("UNRESOLVED_OR_UNVERIFIED_TOPICS")
    if conditional:
        reasons.add("CONDITIONAL_TERMS_REQUIRE_IMPLEMENTATION_EVIDENCE")
    counts = {status: sum(value.status == status for value in normalized.values()) for status in STATUSES}
    return AnswerMatrixResult(
        MATRIX_VERSION,
        "REVIEW_CANDIDATE" if core else "FAIL_CLOSED",
        core,
        sns,
        False,
        core or sns or bool(conditional),
        counts,
        blocking,
        conditional,
        tuple(sorted(reasons)) or ("SANITIZED_MATRIX_COMPLETE", "SEPARATE_GATE_REVIEW_REQUIRED"),
    )


def main() -> int:
    result = assess_answer_matrix({})
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0  # Current unanswered state is an expected, safe state.


if __name__ == "__main__":
    raise SystemExit(main())
