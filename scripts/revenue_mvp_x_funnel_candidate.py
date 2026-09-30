"""Pure, non-posting X funnel candidate gate for DATA LAB."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
from typing import Any, Mapping
from urllib.parse import urlencode

from revenue_mvp_official_answer_matrix import (
    AnswerDecision, assess_answer_matrix, current_entries,
)


VERSION = "0.1"
ORIGIN = "https://datalabx.jp"
PREVIEW_ONLY = "PREVIEW_ONLY"
READY_FOR_MANUAL_POST = "READY_FOR_MANUAL_POST"
BLOCKED = "BLOCKED"
PUBLIC_PATHS = frozenset({"/", "/column-price", "/column-score"})
ITEM_PATHS = frozenset({"/items/"})
ITEM_SORTS = frozenset({"original", "price-asc", "price-desc", "observed-desc", "observed-asc"})
ITEM_PRICE_BANDS = frozenset({"all", "under-1000", "1000-1999", "2000-2999", "3000-plus"})
MANUAL_LINK_TOPICS = frozenset({
    "SNS_TO_SITE_TO_FANZA_FUNNEL",
    "SNS_ACCOUNT_REGISTRATION",
    "PR_AD_AFFILIATE_DISCLOSURE",
})
FORBIDDEN = re.compile(
    r"(?:https?://|www\.|@|#|残りわずか|今だけ|急げ|絶対|公式ランキング|No\.?1)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class XCandidateResult:
    version: str
    status: str
    candidate_text: str | None
    manual_review_required: bool
    manual_post_candidate: bool
    posting_performed: bool
    automatic_post_allowed: bool
    media_allowed: bool
    direct_affiliate_link_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _resolved(decision: AnswerDecision | None) -> bool:
    return decision is not None and (
        decision.status == "ALLOWED"
        or (decision.status == "CONDITIONALLY_ALLOWED" and decision.conditions_verified)
    )


def build_candidate(
    *,
    fact_text: Any,
    landing_path: Any,
    campaign: Any,
    landing_sort: Any = None,
    landing_price_band: Any = None,
    public_data_available: Any = False,
    official_answer_entries: Mapping[str, AnswerDecision] | None = None,
    explicit_human_approval: Any = False,
) -> XCandidateResult:
    reasons: set[str] = set()
    text: str | None = None
    if type(public_data_available) is not bool or type(explicit_human_approval) is not bool:
        reasons.add("BOOLEAN_INPUT_INVALID")
    if (
        not isinstance(fact_text, str) or not fact_text.strip()
        or len(fact_text) > 140 or FORBIDDEN.search(fact_text)
        or any(ord(char) < 32 for char in fact_text)
    ):
        reasons.add("FACT_TEXT_INVALID")
    allowed_paths = PUBLIC_PATHS | (ITEM_PATHS if public_data_available is True else frozenset())
    if not isinstance(landing_path, str) or landing_path not in allowed_paths:
        reasons.add("LANDING_PATH_BLOCKED")
    item_landing = landing_path in ITEM_PATHS
    if landing_sort is not None and (
        not item_landing or landing_sort not in ITEM_SORTS
    ):
        reasons.add("LANDING_SORT_BLOCKED")
    if landing_price_band is not None and (
        not item_landing or landing_price_band not in ITEM_PRICE_BANDS
    ):
        reasons.add("LANDING_PRICE_BAND_BLOCKED")
    if not isinstance(campaign, str) or re.fullmatch(r"[a-z0-9_-]{1,32}", campaign) is None:
        reasons.add("CAMPAIGN_INVALID")
    entries = current_entries() if official_answer_entries is None else official_answer_entries
    answers = assess_answer_matrix(entries)
    manual_link_conditions_verified = (
        not {"MALFORMED_INPUT", "UNKNOWN_TOPIC", "INVALID_DECISION",
             "INVALID_CONDITION_STATE", "CONTRADICTORY_CONDITION_STATE"}
        .intersection(answers.reason_codes)
        and all(_resolved(entries.get(topic)) for topic in MANUAL_LINK_TOPICS)
    )
    if not manual_link_conditions_verified:
        reasons.add("SNS_CONDITIONS_NOT_VERIFIED")

    content_safe = not reasons.intersection({
        "BOOLEAN_INPUT_INVALID", "FACT_TEXT_INVALID", "LANDING_PATH_BLOCKED",
        "CAMPAIGN_INVALID", "LANDING_SORT_BLOCKED", "LANDING_PRICE_BAND_BLOCKED",
    })
    if content_safe:
        query_values = {}
        if landing_sort is not None:
            query_values["sort"] = landing_sort
        if landing_price_band is not None:
            query_values["price_band"] = landing_price_band
        query_values.update({
            "utm_source": "x", "utm_medium": "social", "utm_campaign": campaign,
        })
        query = urlencode(query_values)
        text = (
            f"【PR】{fact_text.strip()}\n\n"
            f"DATA LAB独自集計・非公式\n{ORIGIN}{landing_path}?{query}"
        )
        if len(text) > 280:
            text = None
            reasons.add("POST_LENGTH_EXCEEDED")
            content_safe = False

    manual_candidate = (
        content_safe and manual_link_conditions_verified
        and explicit_human_approval is True
    )
    status = (
        READY_FOR_MANUAL_POST if manual_candidate
        else PREVIEW_ONLY if content_safe
        else BLOCKED
    )
    return XCandidateResult(
        VERSION, status, text, True, manual_candidate, False, False, False,
        False, tuple(sorted(reasons)) or (
            ("MANUAL_POST_CANDIDATE_READY",)
            if manual_candidate
            else ("EXPLICIT_HUMAN_APPROVAL_REQUIRED",)
        ),
    )


def main() -> int:
    result = build_candidate(
        fact_text="DATA LABの公開準備状況を更新しました。",
        landing_path="/", campaign="launch_status",
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
