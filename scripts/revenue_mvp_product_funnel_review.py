"""Pure product-level GA4 outbound-click review with fail-closed input handling."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import json
import re
from typing import Any


VERSION = "0.1"
READY = "READY_FOR_MANUAL_REVIEW"
WAITING = "WAITING_FOR_GA4_PROCESSING"
BLOCKED = "BLOCKED"
SURFACES = frozenset({"product_card", "product_detail"})
PUBLIC_ID = re.compile(r"itm_[0-9a-f]{24}")
ROW_FIELDS = frozenset({"item_id", "surface", "outbound_product_clicks"})


@dataclass(frozen=True)
class ProductFunnelReview:
    version: str
    status: str
    period_start: str | None
    period_end: str | None
    total_outbound_product_clicks: int | None
    observed_product_count: int
    ranked_products: tuple[dict[str, Any], ...]
    disposition: str
    reason_codes: tuple[str, ...]
    production_write_performed: bool = False
    external_write_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["ranked_products"] = list(self.ranked_products)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(status: str, reasons: tuple[str, ...], **changes: Any) -> ProductFunnelReview:
    values = {
        "version": VERSION,
        "status": status,
        "period_start": None,
        "period_end": None,
        "total_outbound_product_clicks": None,
        "observed_product_count": 0,
        "ranked_products": (),
        "disposition": "ADDITIONAL_CONFIRMATION_REQUIRED",
        "reason_codes": reasons,
    }
    values.update(changes)
    return ProductFunnelReview(**values)


def build_review(payload: Any) -> ProductFunnelReview:
    if type(payload) is not dict or set(payload) != {
        "version", "period_start", "period_end", "ga4_processing_complete", "rows"
    }:
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
    if type(payload["ga4_processing_complete"]) is not bool:
        return _result(BLOCKED, ("PROCESSING_STATE_INVALID",))
    rows = payload["rows"]
    if type(rows) is not list or len(rows) > 200:
        return _result(BLOCKED, ("ROW_SET_INVALID",))
    if not payload["ga4_processing_complete"]:
        if rows:
            return _result(BLOCKED, ("UNPROCESSED_ROWS_PRESENT",))
        return _result(
            WAITING,
            ("GA4_PROCESSING_WINDOW_NOT_COMPLETE",),
            period_start=start.isoformat(),
            period_end=end.isoformat(),
        )

    seen: set[tuple[str, str]] = set()
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if type(row) is not dict or set(row) != ROW_FIELDS:
            return _result(BLOCKED, ("ROW_SCHEMA_INVALID",))
        item_id = row["item_id"]
        surface = row["surface"]
        clicks = row["outbound_product_clicks"]
        if not isinstance(item_id, str) or PUBLIC_ID.fullmatch(item_id) is None:
            return _result(BLOCKED, ("ITEM_ID_INVALID",))
        if surface not in SURFACES:
            return _result(BLOCKED, ("SURFACE_INVALID",))
        if type(clicks) is not int or clicks < 0:
            return _result(BLOCKED, ("CLICK_COUNT_INVALID",))
        identity = (item_id, surface)
        if identity in seen:
            return _result(BLOCKED, ("ROW_DUPLICATE",))
        seen.add(identity)
        normalized.append({
            "item_id": item_id,
            "surface": surface,
            "outbound_product_clicks": clicks,
        })

    total = sum(row["outbound_product_clicks"] for row in normalized)
    ranked = tuple(sorted(
        normalized,
        key=lambda row: (-row["outbound_product_clicks"], row["item_id"], row["surface"]),
    ))
    return _result(
        READY,
        ("OBSERVED_CLICKS_READY",) if total else ("NO_OBSERVED_CLICKS",),
        period_start=start.isoformat(),
        period_end=end.isoformat(),
        total_outbound_product_clicks=total,
        observed_product_count=len({row["item_id"] for row in normalized}),
        ranked_products=ranked,
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
