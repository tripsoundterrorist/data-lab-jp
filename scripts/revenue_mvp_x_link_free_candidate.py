"""Pure, non-posting gate for link-free DATA LAB X drafts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
import re
from typing import Any

from revenue_mvp_x_funnel_candidate import x_weighted_length, X_MAX_WEIGHTED_LENGTH


VERSION = "0.1"
PREVIEW_ONLY = "PREVIEW_ONLY"
READY_FOR_MANUAL_POST = "READY_FOR_MANUAL_POST"
BLOCKED = "BLOCKED"
THEMES = frozenset({"data_method", "transparency", "site_operation", "weekly_method"})
SOURCE_ID = re.compile(r"[a-z0-9][a-z0-9._:/-]{0,127}", re.IGNORECASE)
FORBIDDEN = re.compile(
    r"(?:https?://|www\.|@|#|【PR】|PRを含みます|購入|今すぐ|おすすめ|売れ筋|"
    r"残りわずか|急げ|絶対|公式ランキング|No\.?1|アフィリエイト)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LinkFreeCandidate:
    version: str
    status: str
    candidate_text: str | None
    weighted_length: int | None
    theme: str | None
    source_ids: tuple[str, ...]
    source_checked_at: str | None
    manual_review_required: bool
    manual_post_candidate: bool
    posting_performed: bool
    automatic_post_allowed: bool
    link_included: bool
    affiliate_promotion_allowed: bool
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
    source_ids: Any,
    source_checked_at: Any,
    explicit_human_approval: Any = False,
) -> LinkFreeCandidate:
    reasons: set[str] = set()
    text: str | None = None
    weighted_length: int | None = None
    normalized_sources: tuple[str, ...] = ()
    checked_at: str | None = None

    if type(explicit_human_approval) is not bool:
        reasons.add("BOOLEAN_INPUT_INVALID")
    if theme not in THEMES:
        reasons.add("THEME_BLOCKED")
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
        or any(not isinstance(value, str) or SOURCE_ID.fullmatch(value) is None for value in source_ids)
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

    if not reasons:
        text = fact_text.strip()
        weighted_length = x_weighted_length(text)
        if weighted_length > X_MAX_WEIGHTED_LENGTH:
            text = None
            reasons.add("POST_LENGTH_EXCEEDED")

    ready = not reasons and explicit_human_approval is True
    status = READY_FOR_MANUAL_POST if ready else PREVIEW_ONLY if not reasons else BLOCKED
    return LinkFreeCandidate(
        VERSION,
        status,
        text,
        weighted_length,
        theme if theme in THEMES else None,
        normalized_sources,
        checked_at,
        True,
        ready,
        False,
        False,
        False,
        False,
        tuple(sorted(reasons)) or (
            ("MANUAL_LINK_FREE_POST_CANDIDATE_READY",)
            if ready
            else ("EXPLICIT_HUMAN_APPROVAL_REQUIRED",)
        ),
    )


def main() -> int:
    result = build_candidate(
        fact_text=(
            "DATA LABは、取得できた情報と確認時点を分けて記録しています。"
            "確認できない値は推測で補わず、未取得として扱います。"
        ),
        theme="transparency",
        source_ids=["github:docs/policies/sns-x-operations-v0.1.md"],
        source_checked_at="2026-10-01T00:00:00+09:00",
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {PREVIEW_ONLY, READY_FOR_MANUAL_POST} else 2


if __name__ == "__main__":
    raise SystemExit(main())
