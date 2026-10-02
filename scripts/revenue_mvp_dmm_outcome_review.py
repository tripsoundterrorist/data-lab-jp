"""Pure local review boundary for owner-supplied DMM affiliate outcomes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import json
from typing import Any


VERSION = "0.1"
READY = "READY_FOR_MANUAL_REVIEW"
WAITING = "WAITING_FOR_DMM_REPORT_DATA"
BLOCKED = "BLOCKED"
PERIOD_START = "2026-10-02"
PERIOD_END = "2026-10-08"
EARLIEST_REVIEW_DATE = date(2026, 10, 10)
NOT_ACQUIRED = "NOT_ACQUIRED"
NO_DATA = "NO_DATA"
DATA_ACQUIRED = "DATA_ACQUIRED"
REPORT_STATUSES = frozenset({NOT_ACQUIRED, NO_DATA, DATA_ACQUIRED})
ROOT_FIELDS = frozenset({
    "version", "period_start", "period_end", "report_status",
    "affiliate_conversions", "affiliate_revenue_yen",
})


@dataclass(frozen=True)
class DmmOutcomeReview:
    version: str
    status: str
    period_start: str | None
    period_end: str | None
    reviewed_on: str
    report_status: str
    affiliate_conversions: int | None
    affiliate_revenue_yen: int | None
    zero_conversion_period_confirmed: bool
    zero_revenue_period_confirmed: bool
    disposition: str
    expansion_decision_allowed: bool
    production_write_allowed: bool
    external_write_performed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(status: str, reasons: tuple[str, ...], **changes: Any) -> DmmOutcomeReview:
    values = {
        "version": VERSION,
        "status": status,
        "period_start": None,
        "period_end": None,
        "reviewed_on": "INVALID",
        "report_status": NOT_ACQUIRED,
        "affiliate_conversions": None,
        "affiliate_revenue_yen": None,
        "zero_conversion_period_confirmed": False,
        "zero_revenue_period_confirmed": False,
        "disposition": "ADDITIONAL_CONFIRMATION_REQUIRED",
        "expansion_decision_allowed": False,
        "production_write_allowed": False,
        "external_write_performed": False,
        "reason_codes": reasons,
    }
    values.update(changes)
    return DmmOutcomeReview(**values)


def _observed_non_negative_integer(value: Any) -> bool:
    return type(value) is int and value >= 0


def build_review(payload: Any, *, evaluated_on: date | None = None) -> DmmOutcomeReview:
    review_date = date.today() if evaluated_on is None else evaluated_on
    if type(payload) is not dict or set(payload) != ROOT_FIELDS:
        return _result(BLOCKED, ("ROOT_SCHEMA_INVALID",))
    if payload["version"] != VERSION:
        return _result(BLOCKED, ("VERSION_INVALID",))
    try:
        start = date.fromisoformat(payload["period_start"])
        end = date.fromisoformat(payload["period_end"])
    except (TypeError, ValueError):
        return _result(BLOCKED, ("PERIOD_INVALID",))
    if start > end or (end - start).days > 31:
        return _result(BLOCKED, ("PERIOD_INVALID",))
    if start.isoformat() != PERIOD_START or end.isoformat() != PERIOD_END:
        return _result(BLOCKED, ("MEASUREMENT_PERIOD_NOT_EXACT",))
    if type(review_date) is not date:
        return _result(BLOCKED, ("REVIEW_DATE_INVALID",))

    report_status = payload["report_status"]
    if report_status not in REPORT_STATUSES:
        return _result(BLOCKED, ("REPORT_STATUS_INVALID",))
    conversions = payload["affiliate_conversions"]
    revenue_yen = payload["affiliate_revenue_yen"]

    if report_status in {NOT_ACQUIRED, NO_DATA}:
        if conversions != NOT_ACQUIRED or revenue_yen != NOT_ACQUIRED:
            return _result(BLOCKED, ("UNACQUIRED_METRICS_PRESENT",))
        return _result(
            WAITING,
            ("DMM_REPORT_NOT_ACQUIRED",) if report_status == NOT_ACQUIRED
            else ("DMM_REPORT_NO_DATA_NOT_ZERO",),
            period_start=start.isoformat(),
            period_end=end.isoformat(),
            reviewed_on=review_date.isoformat(),
            report_status=report_status,
        )

    if not _observed_non_negative_integer(conversions):
        return _result(BLOCKED, ("AFFILIATE_CONVERSIONS_INVALID",))
    if not _observed_non_negative_integer(revenue_yen):
        return _result(BLOCKED, ("AFFILIATE_REVENUE_INVALID",))
    if review_date < EARLIEST_REVIEW_DATE:
        return _result(
            WAITING,
            ("EARLIEST_REVIEW_DATE_NOT_REACHED",),
            period_start=start.isoformat(),
            period_end=end.isoformat(),
            reviewed_on=review_date.isoformat(),
            report_status=report_status,
        )
    return _result(
        READY,
        ("OBSERVED_DMM_OUTCOMES_READY",),
        period_start=start.isoformat(),
        period_end=end.isoformat(),
        reviewed_on=review_date.isoformat(),
        report_status=report_status,
        affiliate_conversions=conversions,
        affiliate_revenue_yen=revenue_yen,
        zero_conversion_period_confirmed=conversions == 0,
        zero_revenue_period_confirmed=revenue_yen == 0,
    )


def main() -> int:
    import sys
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        result = _result(BLOCKED, ("JSON_INVALID",))
    else:
        result = build_review(payload)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {READY, WAITING} else 2


if __name__ == "__main__":
    raise SystemExit(main())
