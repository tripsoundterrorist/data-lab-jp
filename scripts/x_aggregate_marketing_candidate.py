"""Fail-closed proposal gate for aggregate DATA LAB X marketing drafts.

This module never authorizes or performs an X post. Its highest state is
READY_FOR_COMPLIANCE_REVIEW.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import re
from typing import Any

VERSION = "0.1"
X_MAX_WEIGHTED_LENGTH = 280
X_SHORTENED_URL_LENGTH = 23
URL_TOKEN = re.compile(r"https?://[^\s]+", re.IGNORECASE)
READY_FOR_COMPLIANCE_REVIEW = "READY_FOR_COMPLIANCE_REVIEW"
BLOCKED = "BLOCKED"
THEMES = frozenset(
    {"price_distribution", "catalog_snapshot", "verified_change", "new_data"}
)
SOURCE_TYPES = frozenset({"public_site_snapshot", "reviewed_aggregate"})
SOURCE_ID = re.compile(r"[a-z0-9][a-z0-9._:/-]{0,191}", re.IGNORECASE)
FORBIDDEN = re.compile(
    r"(?:https?://|www\.|@|#|【PR】|PRを含みます|アフィリエイト|購入|今すぐ|"
    r"おすすめ|絶対|必見|残りわずか|急げ|売上No\.?1|人気No\.?1)",
    re.IGNORECASE,
)


def x_weighted_length(value: str) -> int:
    """Conservatively mirror X counting: CJK/non-ASCII=2, each URL=23."""

    total = 0
    cursor = 0
    for match in URL_TOKEN.finditer(value):
        total += sum(1 if ord(char) <= 0x7F else 2 for char in value[cursor:match.start()])
        total += X_SHORTENED_URL_LENGTH
        cursor = match.end()
    return total + sum(1 if ord(char) <= 0x7F else 2 for char in value[cursor:])


@dataclass(frozen=True)
class AggregateMarketingCandidate:
    version: str
    status: str
    candidate_text: str | None
    weighted_length: int | None
    theme: str | None
    source_type: str | None
    source_ids: tuple[str, ...]
    source_checked_at: str | None
    aggregate_facts: dict[str, int | float]
    compliance_review_required: bool
    manual_post_candidate: bool
    posting_performed: bool
    automatic_post_allowed: bool
    link_included: bool
    affiliate_promotion_allowed: bool
    product_media_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["source_ids"] = list(self.source_ids)
        value["reason_codes"] = list(self.reason_codes)
        return value


def build_candidate(
    *,
    fact_text: Any,
    theme: Any,
    source_type: Any,
    source_ids: Any,
    source_checked_at: Any,
    aggregate_facts: Any,
) -> AggregateMarketingCandidate:
    reasons: set[str] = set()
    text: str | None = None
    weighted_length: int | None = None
    normalized_sources: tuple[str, ...] = ()
    checked_at: str | None = None
    normalized_facts: dict[str, int | float] = {}

    if theme not in THEMES:
        reasons.add("THEME_BLOCKED")
    if source_type not in SOURCE_TYPES:
        reasons.add("SOURCE_TYPE_BLOCKED")
    if (
        not isinstance(fact_text, str)
        or not fact_text.strip()
        or len(fact_text) > 140
        or FORBIDDEN.search(fact_text)
        or any(ord(char) < 32 for char in fact_text)
    ):
        reasons.add("FACT_TEXT_INVALID")
    if (
        type(source_ids) not in {list, tuple}
        or not 1 <= len(source_ids) <= 5
        or any(
            not isinstance(value, str) or SOURCE_ID.fullmatch(value) is None
            for value in source_ids
        )
        or len(set(source_ids)) != len(source_ids)
    ):
        reasons.add("SOURCE_IDS_INVALID")
    else:
        normalized_sources = tuple(source_ids)
    if not isinstance(source_checked_at, str):
        reasons.add("SOURCE_CHECKED_AT_INVALID")
    else:
        try:
            parsed = datetime.fromisoformat(source_checked_at.replace("Z", "+00:00"))
        except ValueError:
            reasons.add("SOURCE_CHECKED_AT_INVALID")
        else:
            if parsed.tzinfo is None:
                reasons.add("SOURCE_CHECKED_AT_INVALID")
            else:
                checked_at = source_checked_at
    if (
        not isinstance(aggregate_facts, dict)
        or not 1 <= len(aggregate_facts) <= 12
        or any(
            not isinstance(key, str)
            or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key) is None
            or type(value) not in {int, float}
            or value < 0
            for key, value in aggregate_facts.items()
        )
    ):
        reasons.add("AGGREGATE_FACTS_INVALID")
    else:
        normalized_facts = dict(aggregate_facts)

    if not reasons:
        text = fact_text.strip()
        weighted_length = x_weighted_length(text)
        if weighted_length > X_MAX_WEIGHTED_LENGTH:
            text = None
            reasons.add("POST_LENGTH_EXCEEDED")

    status = READY_FOR_COMPLIANCE_REVIEW if not reasons else BLOCKED
    return AggregateMarketingCandidate(
        VERSION,
        status,
        text,
        weighted_length,
        theme if theme in THEMES else None,
        source_type if source_type in SOURCE_TYPES else None,
        normalized_sources,
        checked_at,
        normalized_facts,
        True,
        False,
        False,
        False,
        False,
        False,
        False,
        tuple(sorted(reasons)) or ("COMPLIANCE_REVIEW_REQUIRED",),
    )
