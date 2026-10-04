"""Pure weekly X-to-site funnel review with explicit missing-data handling."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
import json
import re
from typing import Any


VERSION = "0.1"
READY = "READY_FOR_MANUAL_REVIEW"
BLOCKED = "BLOCKED"
NOT_ACQUIRED = "NOT_ACQUIRED"
THEMES = frozenset({
    "price_change", "price_distribution", "ranking_change", "new_or_updated", "data_literacy",
    "transparency", "weekly_summary", "site_update",
})
METRICS = (
    "impressions", "non_follower_reach", "engagements", "profile_visits",
    "follows", "link_clicks", "ga_sessions", "outbound_product_clicks",
)
ROW_FIELDS = frozenset({
    "post_url_or_id", "posted_at_jst", "theme", "pr_link", "campaign", *METRICS,
})
CAMPAIGN = re.compile(r"[a-z0-9_-]{1,32}")


@dataclass(frozen=True)
class WeeklyReview:
    version: str
    status: str
    period_start: str | None
    period_end: str | None
    post_count: int
    metric_summaries: dict[str, dict[str, Any]]
    post_rates: tuple[dict[str, Any], ...]
    disposition: str
    reason_codes: tuple[str, ...]
    external_write_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["post_rates"] = list(self.post_rates)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(*reasons: str) -> WeeklyReview:
    return WeeklyReview(
        VERSION, BLOCKED, None, None, 0, {}, (),
        "ADDITIONAL_CONFIRMATION_REQUIRED", tuple(sorted(set(reasons))),
    )


def _metric(value: Any) -> bool:
    return value == NOT_ACQUIRED or (type(value) is int and value >= 0)


def _rate(numerator: Any, denominator: Any) -> float | str:
    if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
        return NOT_ACQUIRED
    return round(numerator / denominator, 6)


def build_review(payload: Any) -> WeeklyReview:
    if type(payload) is not dict or set(payload) != {"version", "period_start", "period_end", "posts"}:
        return _blocked("ROOT_SCHEMA_INVALID")
    if payload.get("version") != VERSION:
        return _blocked("VERSION_INVALID")
    try:
        period_start = date.fromisoformat(payload["period_start"])
        period_end = date.fromisoformat(payload["period_end"])
    except (TypeError, ValueError):
        return _blocked("PERIOD_INVALID")
    if period_start.weekday() != 0 or period_end.weekday() != 6 or (period_end - period_start).days != 6:
        return _blocked("PERIOD_NOT_MONDAY_TO_SUNDAY")
    posts = payload.get("posts")
    if type(posts) is not list or not 1 <= len(posts) <= 100:
        return _blocked("POST_SET_INVALID")

    reasons: set[str] = set()
    identities: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for row in posts:
        if type(row) is not dict or set(row) != ROW_FIELDS:
            reasons.add("POST_SCHEMA_INVALID")
            continue
        identity = row.get("post_url_or_id")
        if not isinstance(identity, str) or not identity.strip() or len(identity) > 256:
            reasons.add("POST_IDENTITY_INVALID")
        elif identity in identities:
            reasons.add("POST_IDENTITY_DUPLICATE")
        else:
            identities.add(identity)
        try:
            posted = datetime.fromisoformat(row["posted_at_jst"])
            if posted.utcoffset() is None or posted.utcoffset().total_seconds() != 9 * 3600:
                raise ValueError
            if not period_start <= posted.date() <= period_end:
                reasons.add("POST_OUTSIDE_PERIOD")
        except (TypeError, ValueError):
            reasons.add("POSTED_AT_JST_INVALID")
        if row.get("theme") not in THEMES:
            reasons.add("THEME_INVALID")
        if type(row.get("pr_link")) is not bool:
            reasons.add("PR_LINK_INVALID")
        campaign = row.get("campaign")
        if campaign != NOT_ACQUIRED and (
            not isinstance(campaign, str) or CAMPAIGN.fullmatch(campaign) is None
        ):
            reasons.add("CAMPAIGN_INVALID")
        if any(not _metric(row.get(metric)) for metric in METRICS):
            reasons.add("METRIC_INVALID")
        if (
            type(row.get("link_clicks")) is int
            and type(row.get("impressions")) is int
            and row["link_clicks"] > row["impressions"]
        ):
            reasons.add("CLICK_COUNT_EXCEEDS_IMPRESSIONS")
        normalized.append(row)
    if reasons:
        return _blocked(*reasons)

    summaries: dict[str, dict[str, Any]] = {}
    for metric in METRICS:
        acquired = [row[metric] for row in normalized if type(row[metric]) is int]
        summaries[metric] = {
            "acquired_post_count": len(acquired),
            "missing_post_count": len(normalized) - len(acquired),
            "total": sum(acquired) if len(acquired) == len(normalized) else NOT_ACQUIRED,
        }
    rates = tuple({
        "post_url_or_id": row["post_url_or_id"],
        "campaign": row["campaign"],
        "x_link_ctr": _rate(row["link_clicks"], row["impressions"]),
        "site_cta_rate": _rate(row["outbound_product_clicks"], row["ga_sessions"]),
    } for row in normalized)
    missing = any(summary["missing_post_count"] for summary in summaries.values())
    return WeeklyReview(
        VERSION, READY, period_start.isoformat(), period_end.isoformat(),
        len(normalized), summaries, rates, "ADDITIONAL_CONFIRMATION_REQUIRED",
        ("MISSING_VALUES_PRESERVED",) if missing else ("OBSERVED_TOTALS_READY",),
    )


def main() -> int:
    import sys
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        result = _blocked("JSON_INVALID")
    else:
        result = build_review(payload)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
