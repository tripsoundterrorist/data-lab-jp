"""Combine validated GA4 and DMM aggregates without claiming attribution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import json
from typing import Any

import revenue_mvp_dmm_outcome_review as dmm_review
import revenue_mvp_product_funnel_review_receipt as ga4_receipt


VERSION = "0.1"
READY = "READY_FOR_MANUAL_REVIEW"
WAITING = "WAITING_FOR_COMPLETE_FUNNEL_INPUTS"
BLOCKED = "BLOCKED"
NOT_ACQUIRED = "NOT_ACQUIRED"
ROOT_FIELDS = frozenset({"version", "ga4_input", "dmm_input"})


@dataclass(frozen=True)
class FunnelOutcomeReview:
    version: str
    status: str
    period_start: str | None
    period_end: str | None
    reviewed_on: str
    outbound_product_clicks: int | None
    affiliate_conversions: int | None
    affiliate_revenue_yen: int | None
    same_period_conversion_click_ratio: float | str
    same_period_revenue_per_click_yen: float | str
    attribution_status: str
    disposition: str
    expansion_decision_allowed: bool
    production_write_allowed: bool
    external_write_performed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(status: str, reasons: tuple[str, ...], **changes: Any) -> FunnelOutcomeReview:
    values = {
        "version": VERSION,
        "status": status,
        "period_start": None,
        "period_end": None,
        "reviewed_on": "INVALID",
        "outbound_product_clicks": None,
        "affiliate_conversions": None,
        "affiliate_revenue_yen": None,
        "same_period_conversion_click_ratio": NOT_ACQUIRED,
        "same_period_revenue_per_click_yen": NOT_ACQUIRED,
        "attribution_status": "NOT_ESTABLISHED_BY_AGGREGATES",
        "disposition": "ADDITIONAL_CONFIRMATION_REQUIRED",
        "expansion_decision_allowed": False,
        "production_write_allowed": False,
        "external_write_performed": False,
        "reason_codes": reasons,
    }
    values.update(changes)
    return FunnelOutcomeReview(**values)


def build_review(payload: Any, *, evaluated_on: date | None = None) -> FunnelOutcomeReview:
    review_date = date.today() if evaluated_on is None else evaluated_on
    if type(payload) is not dict or set(payload) != ROOT_FIELDS:
        return _result(BLOCKED, ("ROOT_SCHEMA_INVALID",))
    if payload["version"] != VERSION:
        return _result(BLOCKED, ("VERSION_INVALID",))
    if type(review_date) is not date:
        return _result(BLOCKED, ("REVIEW_DATE_INVALID",))

    ga4 = ga4_receipt.build(payload["ga4_input"], evaluated_on=review_date)
    dmm = dmm_review.build_review(payload["dmm_input"], evaluated_on=review_date)
    reasons: set[str] = set()
    if ga4.status != ga4_receipt.COMPLETED:
        reasons.add("GA4_PRODUCT_FUNNEL_REVIEW_NOT_COMPLETE")
    if dmm.status != dmm_review.READY:
        reasons.add("DMM_OUTCOME_REVIEW_NOT_READY")
    same_period = (
        ga4.period_start == dmm.period_start == ga4_receipt.PERIOD_START
        and ga4.period_end == dmm.period_end == ga4_receipt.PERIOD_END
    )
    if not same_period:
        reasons.add("MEASUREMENT_PERIOD_MISMATCH")
    if reasons:
        return _result(
            WAITING,
            tuple(sorted(reasons)),
            period_start=ga4.period_start if ga4.period_start == dmm.period_start else None,
            period_end=ga4.period_end if ga4.period_end == dmm.period_end else None,
            reviewed_on=review_date.isoformat(),
        )

    clicks = ga4.total_outbound_product_clicks
    conversions = dmm.affiliate_conversions
    revenue_yen = dmm.affiliate_revenue_yen
    if type(clicks) is not int or type(conversions) is not int or type(revenue_yen) is not int:
        return _result(BLOCKED, ("VALIDATED_TOTALS_MISSING",))

    ratio: float | str = NOT_ACQUIRED
    revenue_per_click: float | str = NOT_ACQUIRED
    result_reasons = {"SAME_PERIOD_AGGREGATES_NOT_USER_LEVEL_ATTRIBUTION"}
    if clicks > 0:
        ratio = round(conversions / clicks, 6)
        revenue_per_click = round(revenue_yen / clicks, 2)
        result_reasons.add("SAME_PERIOD_PROXY_METRICS_READY")
    else:
        result_reasons.add("ZERO_CLICK_DENOMINATOR")

    return _result(
        READY,
        tuple(sorted(result_reasons)),
        period_start=ga4.period_start,
        period_end=ga4.period_end,
        reviewed_on=review_date.isoformat(),
        outbound_product_clicks=clicks,
        affiliate_conversions=conversions,
        affiliate_revenue_yen=revenue_yen,
        same_period_conversion_click_ratio=ratio,
        same_period_revenue_per_click_yen=revenue_per_click,
    )


def main() -> int:
    import sys
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = None
    result = build_review(payload)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {READY, WAITING} else 2


if __name__ == "__main__":
    raise SystemExit(main())
