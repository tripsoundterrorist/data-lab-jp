"""Pure, collection-only validation for normalized doujin price facts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


VERSION = "2026-10-02.1"
CONTENT_TYPES = frozenset({"doujin", "doujin_bl", "doujin_tl"})


@dataclass(frozen=True)
class DoujinPriceObservation:
    version: str
    content_type: str
    observed_at: datetime
    current_price: int | None
    list_price: int | None
    discount_amount: int | None
    discount_rate: int | float | None


@dataclass(frozen=True)
class DoujinPriceSnapshotCandidate:
    version: str
    status: str
    normalized_price_structure_valid: bool
    current_price_fact_candidate: bool
    discount_fact_candidate: bool
    exact_source_semantics_confirmed: bool
    historical_retention_allowed: bool
    public_display_allowed: bool
    analysis_allowed: bool
    publication_gate_change_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["reason_codes"] = list(self.reason_codes)
        return result


def _result(
    *, valid: bool, current: bool = False, discount: bool = False, reason: str
) -> DoujinPriceSnapshotCandidate:
    return DoujinPriceSnapshotCandidate(
        VERSION,
        "READY_FOR_PRICE_SEMANTICS_REVIEW" if valid else "FAIL_CLOSED",
        valid,
        current,
        discount,
        False,
        False,
        False,
        False,
        False,
        (reason,),
    )


def _money(value: Any, *, optional: bool = False) -> bool:
    return (optional and value is None) or (
        type(value) is int and value >= 0
    )


def assess_doujin_price_snapshot(value: Any) -> DoujinPriceSnapshotCandidate:
    """Validate normalized arithmetic without approving storage or display."""

    try:
        if type(value) is not DoujinPriceObservation:
            return _result(valid=False, reason="PRICE_OBSERVATION_CONTRACT_INVALID")
        if value.version != VERSION or value.content_type not in CONTENT_TYPES:
            return _result(valid=False, reason="PRICE_OBSERVATION_SCOPE_INVALID")
        if not isinstance(value.observed_at, datetime) or value.observed_at.tzinfo is None:
            return _result(valid=False, reason="PRICE_OBSERVATION_TIME_INVALID")
        if not _money(value.current_price, optional=True):
            return _result(valid=False, reason="CURRENT_PRICE_INVALID")
        if not _money(value.list_price, optional=True):
            return _result(valid=False, reason="LIST_PRICE_INVALID")
        if value.current_price is None:
            if any(
                part is not None
                for part in (
                    value.list_price,
                    value.discount_amount,
                    value.discount_rate,
                )
            ):
                return _result(valid=False, reason="PRICE_FACTS_WITHOUT_CURRENT_PRICE")
            return _result(valid=True, reason="PRICE_UNAVAILABLE_REVIEW_CANDIDATE")
        if value.list_price is None:
            if value.discount_amount is not None or value.discount_rate is not None:
                return _result(valid=False, reason="DISCOUNT_WITHOUT_LIST_PRICE")
            return _result(
                valid=True,
                current=True,
                reason="CURRENT_PRICE_ONLY_REVIEW_CANDIDATE",
            )
        if value.list_price < value.current_price:
            return _result(valid=False, reason="LIST_PRICE_BELOW_CURRENT_PRICE")
        expected_amount = value.list_price - value.current_price
        if type(value.discount_amount) is not int or value.discount_amount != expected_amount:
            return _result(valid=False, reason="DISCOUNT_AMOUNT_MISMATCH")
        expected_rate = (
            round(expected_amount * 100 / value.list_price, 2)
            if value.list_price
            else None
        )
        if (
            value.discount_rate is None
            if expected_rate is not None
            else value.discount_rate is not None
        ):
            return _result(valid=False, reason="DISCOUNT_RATE_PRESENCE_MISMATCH")
        if expected_rate is not None and (
            isinstance(value.discount_rate, bool)
            or not isinstance(value.discount_rate, (int, float))
            or float(value.discount_rate) != expected_rate
        ):
            return _result(valid=False, reason="DISCOUNT_RATE_MISMATCH")
        return _result(
            valid=True,
            current=True,
            discount=expected_amount > 0,
            reason="NORMALIZED_PRICE_ARITHMETIC_REVIEW_CANDIDATE",
        )
    except Exception:
        return _result(valid=False, reason="PRICE_SNAPSHOT_ASSESSMENT_ERROR")


__all__ = [
    "CONTENT_TYPES",
    "VERSION",
    "DoujinPriceObservation",
    "DoujinPriceSnapshotCandidate",
    "assess_doujin_price_snapshot",
]
