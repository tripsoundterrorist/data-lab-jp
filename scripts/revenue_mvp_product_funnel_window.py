"""Fail-closed timing boundary for the first product-level GA4 funnel review."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
import json
from pathlib import Path
from typing import Any


VERSION = "0.1"
WAITING = "WAITING_FOR_PRODUCT_FUNNEL_WINDOW"
READY = "PRODUCT_FUNNEL_WINDOW_READY_FOR_MANUAL_EXPORT"
BLOCKED = "PRODUCT_FUNNEL_WINDOW_BLOCKED"
ROOT = Path(__file__).resolve().parents[1]
DIMENSIONS_EVIDENCE = (
    ROOT / "docs" / "evidence" / "revenue-mvp-ga4-product-dimensions-20261001.json"
)
MINIMUM_COMPLETE_DAYS = 7
PROCESSING_DELAY_DAYS = 2


@dataclass(frozen=True)
class ProductFunnelWindow:
    version: str
    status: str
    registration_date: str | None
    period_start: str | None
    period_end: str | None
    earliest_manual_review_date: str | None
    minimum_complete_days: int
    processing_delay_days: int
    product_funnel_window_closed: bool
    ga4_export_allowed: bool
    expansion_decision_allowed: bool
    production_change_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _blocked(reason: str) -> ProductFunnelWindow:
    return ProductFunnelWindow(
        VERSION, BLOCKED, None, None, None, None,
        MINIMUM_COMPLETE_DAYS, PROCESSING_DELAY_DAYS,
        False, False, False, False, (reason,),
    )


def assess(evidence: Any, evaluated_on: date) -> ProductFunnelWindow:
    if type(evidence) is not dict or type(evaluated_on) is not date:
        return _blocked("FUNNEL_WINDOW_INPUT_INVALID")
    expected = {
        "version", "status", "confirmed_at", "source", "property",
        "custom_dimensions", "site_collection_commit",
        "expected_reporting_delay", "retroactive", "next_action",
        "production_site_write_performed", "ga4_change_performed_by_owner",
    }
    if set(evidence) != expected:
        return _blocked("DIMENSION_EVIDENCE_SCHEMA_INVALID")
    dimensions = evidence.get("custom_dimensions")
    if (
        evidence.get("version") != "0.1"
        or evidence.get("status") != "GA4_PRODUCT_FUNNEL_DIMENSIONS_REGISTERED"
        or evidence.get("property") != "DATA LAB"
        or evidence.get("expected_reporting_delay") != "24_TO_48_HOURS"
        or evidence.get("retroactive") is not False
        or evidence.get("production_site_write_performed") is not False
        or evidence.get("ga4_change_performed_by_owner") is not True
        or type(dimensions) is not list
        or dimensions != [
            {"display_name": "Funnel Surface", "scope": "EVENT",
             "event_parameter": "funnel_surface"},
            {"display_name": "Item ID", "scope": "EVENT",
             "event_parameter": "item_id"},
        ]
    ):
        return _blocked("DIMENSION_EVIDENCE_INVALID")
    try:
        registered = date.fromisoformat(evidence["confirmed_at"])
    except (TypeError, ValueError):
        return _blocked("REGISTRATION_DATE_INVALID")

    period_start = registered + timedelta(days=1)
    period_end = period_start + timedelta(days=MINIMUM_COMPLETE_DAYS - 1)
    review_date = period_end + timedelta(days=PROCESSING_DELAY_DAYS)
    ready = evaluated_on >= review_date
    return ProductFunnelWindow(
        VERSION,
        READY if ready else WAITING,
        registered.isoformat(),
        period_start.isoformat(),
        period_end.isoformat(),
        review_date.isoformat(),
        MINIMUM_COMPLETE_DAYS,
        PROCESSING_DELAY_DAYS,
        ready,
        ready,
        False,
        False,
        ("MANUAL_GA4_EXPORT_REQUIRED",) if ready else
        ("MINIMUM_COMPLETE_WINDOW_OR_PROCESSING_DELAY_PENDING",),
    )


def current_evidence() -> dict[str, Any] | None:
    try:
        value = json.loads(DIMENSIONS_EVIDENCE.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if type(value) is dict else None


def main() -> int:
    result = assess(current_evidence(), date(2026, 10, 1))
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {WAITING, READY} else 2


if __name__ == "__main__":
    raise SystemExit(main())
