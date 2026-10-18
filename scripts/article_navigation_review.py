"""Offline aggregate review only; no GA4 access, rates, ranking or write authority.

Input is a manually verified, complete report for the three routes. The first
whole JST day after dimension registration is 2026-10-19. Partial launch-day
and realtime observations are not accepted as processed outcome data.
Non-test event counts do not establish unique readers, human traffic or sales.
"""
from datetime import date, datetime, timedelta, timezone

ROUTES = ("coupon_to_price", "device_to_price", "price_to_items")
FIELDS = {"version", "period_start", "period_end", "observed_at",
          "source", "acquired", "processing_complete", "rows"}
ROW_FIELDS = {"navigation_route", "event_count", "test_status", "test_count"}
JST = timezone(timedelta(hours=9))


def build_review(payload, *, now=None):
    result = {"status": "BLOCKED", "reason": "INVALID_INPUT",
              "total_events": None, "non_test_events": None, "routes": [],
              "rates": "NOT_ACQUIRED", "attribution": "NOT_ESTABLISHED",
              "external_write_performed": False, "production_write_performed": False}
    if type(payload) is not dict or set(payload) != FIELDS:
        return result
    if payload["version"] != "0.1" or payload["source"] != "GA4_PROCESSED_REPORT":
        return result
    if any(type(payload[k]) is not bool for k in ("acquired", "processing_complete")):
        return result
    try:
        start = date.fromisoformat(payload["period_start"])
        end = date.fromisoformat(payload["period_end"])
        observed = datetime.fromisoformat(payload["observed_at"])
        clock = now if now is not None else datetime.now(timezone.utc)
        if observed.utcoffset() is None or clock.utcoffset() is None:
            return result
        if start > end or (end - start).days > 30 or observed > clock:
            return result
        observed_day = observed.astimezone(JST).date()
    except (ValueError, TypeError, AttributeError, OverflowError):
        return result
    result.update(period_start=start.isoformat(), period_end=end.isoformat(),
                  observed_at=observed.isoformat())
    rows = payload["rows"]
    if type(rows) is not list:
        return result
    if not payload["acquired"] or not payload["processing_complete"]:
        if rows:
            return result
        result.update(status="NOT_ACQUIRED", reason="REPORT_MISSING_OR_UNPROCESSED")
        return result
    if start < date(2026, 10, 19) or observed_day <= end:
        result["reason"] = "INCOMPLETE_OR_PRE_REGISTRATION_PERIOD"
        return result
    if len(rows) != len(ROUTES):
        result["reason"] = "EXPLICIT_THREE_ROUTE_COUNTS_REQUIRED"
        return result
    normalized = {}
    for row in rows:
        if type(row) is not dict or set(row) != ROW_FIELDS:
            return result
        route = row["navigation_route"]
        if type(route) is not str or route not in ROUTES or route in normalized:
            return result
        count, test = row["event_count"], row["test_count"]
        if type(count) is not int or count < 0:
            return result
        status = row["test_status"]
        if status == "VERIFIED":
            if type(test) is not int or not 0 <= test <= count:
                return result
            reader = count - test
        elif status == "UNCONFIRMED" and test is None:
            reader = None
        else:
            return result
        normalized[route] = {"navigation_route": route, "event_count": count,
                             "test_status": status, "test_count": test,
                             "non_test_events": reader}
    result["routes"] = [normalized[r] for r in ROUTES]
    result["total_events"] = sum(row["event_count"] for row in result["routes"])
    if all(row["non_test_events"] is not None for row in result["routes"]):
        result.update(status="READY_FOR_MANUAL_REVIEW", reason="TEST_COUNTS_VERIFIED",
                      non_test_events=sum(row["non_test_events"] for row in result["routes"]))
    else:
        result.update(status="ADDITIONAL_CONFIRMATION_REQUIRED",
                      reason="TEST_CONTAMINATION_UNCONFIRMED")
    return result
