"""Aggregate-only receipt for the first completed GA4 product-funnel review."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

import revenue_mvp_product_funnel_review as review

VERSION = "0.1"
COMPLETED = "PRODUCT_FUNNEL_REVIEW_COMPLETED"
BLOCKED = "PRODUCT_FUNNEL_REVIEW_RECEIPT_BLOCKED"
PERIOD_START = "2026-10-02"
PERIOD_END = "2026-10-08"


@dataclass(frozen=True)
class FunnelReviewReceipt:
    version: str
    status: str
    period_start: str | None
    period_end: str | None
    product_funnel_review_completed: bool
    total_outbound_product_clicks: int | None
    observed_product_count: int
    zero_click_period_confirmed: bool
    expansion_decision_allowed: bool
    production_write_allowed: bool
    external_write_performed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def build(payload: Any) -> FunnelReviewReceipt:
    result = review.build_review(payload)
    exact_period = result.period_start == PERIOD_START and result.period_end == PERIOD_END
    complete = result.status == review.READY and exact_period
    reasons: set[str] = set()
    if result.status != review.READY:
        reasons.add("GA4_REVIEW_NOT_READY")
    if not exact_period:
        reasons.add("MEASUREMENT_PERIOD_NOT_EXACT")
    return FunnelReviewReceipt(
        VERSION, COMPLETED if complete else BLOCKED,
        result.period_start, result.period_end, complete,
        result.total_outbound_product_clicks if complete else None,
        result.observed_product_count if complete else 0,
        complete and result.total_outbound_product_clicks == 0,
        False, False, False, tuple(sorted(reasons)),
    )


def main() -> int:
    import sys
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = None
    result = build(payload)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == COMPLETED else 2


if __name__ == "__main__":
    raise SystemExit(main())
