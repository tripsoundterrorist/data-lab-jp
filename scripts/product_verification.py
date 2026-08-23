"""Pure product API observation classification for DATA LAB.

This module describes only what an abstract API response showed.  It must not
turn absence or errors into product availability, lifecycle, or publication
decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re
from typing import Any, Mapping


class Observation(str, Enum):
    API_ITEM_VISIBLE = "API_ITEM_VISIBLE"
    API_ITEM_NOT_RETURNED = "API_ITEM_NOT_RETURNED"
    API_RATE_LIMITED = "API_RATE_LIMITED"
    API_ERROR = "API_ERROR"
    CID_MISMATCH = "CID_MISMATCH"
    MULTIPLE_ITEMS_RETURNED = "MULTIPLE_ITEMS_RETURNED"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    UNKNOWN = "UNKNOWN"


class ErrorClass(str, Enum):
    RATE_LIMITED = "rate_limited"
    TRANSIENT_ERROR = "transient_error"
    PERMANENT_ERROR = "permanent_error"
    UNKNOWN_ERROR = "unknown_error"


@dataclass(frozen=True)
class VerificationObservation:
    observation: Observation
    observed_at: datetime | None
    expected_content_id_match: bool | None
    affiliate_link_observed: bool | None
    source_status_code: int | str | None
    reason_codes: tuple[str, ...]


_TOP_LEVEL_FIELDS = frozenset(
    {
        "expected_content_id",
        "observed_at",
        "call_status",
        "error_class",
        "source_status_code",
        "result_count",
        "items",
    }
)
_ITEM_FIELDS = frozenset({"content_id", "affiliate_link_present"})
_CONTENT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_STATUS_TEXT_RE = re.compile(r"[A-Za-z0-9_.-]{1,64}\Z")


def _result(
    observation: Observation,
    *,
    observed_at: datetime | None,
    source_status_code: int | str | None,
    reason: str,
    expected_content_id_match: bool | None = None,
    affiliate_link_observed: bool | None = None,
) -> VerificationObservation:
    return VerificationObservation(
        observation=observation,
        observed_at=observed_at,
        expected_content_id_match=expected_content_id_match,
        affiliate_link_observed=affiliate_link_observed,
        source_status_code=source_status_code,
        reason_codes=(reason,),
    )


def _valid_source_status(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return 0 <= value <= 999
    return isinstance(value, str) and _STATUS_TEXT_RE.fullmatch(value) is not None


def _valid_timestamp(value: Any, as_of: datetime) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and as_of.tzinfo is not None
        and value <= as_of
    )


def evaluate_product_verification(
    payload: Mapping[str, Any], *, as_of: datetime
) -> VerificationObservation:
    """Classify a sanitized, abstract API observation using a strict contract."""

    observed_at: datetime | None = None
    source_status_code: int | str | None = None
    try:
        if not isinstance(payload, Mapping) or set(payload) != _TOP_LEVEL_FIELDS:
            return _result(
                Observation.MALFORMED_RESPONSE,
                observed_at=None,
                source_status_code=None,
                reason="INVALID_CONTRACT_FIELDS",
            )

        observed_at = payload["observed_at"]
        source_status_code = payload["source_status_code"]
        if not _valid_timestamp(observed_at, as_of):
            return _result(
                Observation.MALFORMED_RESPONSE,
                observed_at=None,
                source_status_code=None,
                reason="INVALID_OBSERVED_AT",
            )
        if not _valid_source_status(source_status_code):
            return _result(
                Observation.MALFORMED_RESPONSE,
                observed_at=observed_at,
                source_status_code=None,
                reason="INVALID_SOURCE_STATUS_CODE",
            )

        expected_content_id = payload["expected_content_id"]
        if not isinstance(expected_content_id, str) or not _CONTENT_ID_RE.fullmatch(
            expected_content_id
        ):
            return _result(
                Observation.MALFORMED_RESPONSE,
                observed_at=observed_at,
                source_status_code=source_status_code,
                reason="INVALID_EXPECTED_CONTENT_ID",
            )

        call_status = payload["call_status"]
        error_value = payload["error_class"]
        result_count = payload["result_count"]
        items = payload["items"]

        if call_status == "failure":
            if result_count is not None or items != []:
                return _result(
                    Observation.MALFORMED_RESPONSE,
                    observed_at=observed_at,
                    source_status_code=source_status_code,
                    reason="FAILURE_CONTAINS_RESULT_DATA",
                )
            try:
                error_class = ErrorClass(error_value)
            except (TypeError, ValueError):
                return _result(
                    Observation.UNKNOWN,
                    observed_at=observed_at,
                    source_status_code=source_status_code,
                    reason="UNRECOGNIZED_ERROR_CLASS",
                )
            if error_class is ErrorClass.RATE_LIMITED:
                return _result(
                    Observation.API_RATE_LIMITED,
                    observed_at=observed_at,
                    source_status_code=source_status_code,
                    reason="SOURCE_RATE_LIMITED",
                )
            if error_class is ErrorClass.UNKNOWN_ERROR:
                return _result(
                    Observation.UNKNOWN,
                    observed_at=observed_at,
                    source_status_code=source_status_code,
                    reason="SOURCE_UNKNOWN_ERROR",
                )
            return _result(
                Observation.API_ERROR,
                observed_at=observed_at,
                source_status_code=source_status_code,
                reason=(
                    "SOURCE_TRANSIENT_ERROR"
                    if error_class is ErrorClass.TRANSIENT_ERROR
                    else "SOURCE_PERMANENT_ERROR"
                ),
            )

        if call_status != "success" or error_value is not None:
            return _result(
                Observation.MALFORMED_RESPONSE,
                observed_at=observed_at,
                source_status_code=source_status_code,
                reason="INVALID_CALL_STATUS",
            )
        if (
            isinstance(result_count, bool)
            or not isinstance(result_count, int)
            or result_count < 0
            or not isinstance(items, list)
        ):
            return _result(
                Observation.MALFORMED_RESPONSE,
                observed_at=observed_at,
                source_status_code=source_status_code,
                reason="INVALID_RESULT_SHAPE",
            )
        if result_count != len(items):
            return _result(
                Observation.MALFORMED_RESPONSE,
                observed_at=observed_at,
                source_status_code=source_status_code,
                reason="RESULT_COUNT_ITEMS_MISMATCH",
            )
        if not items:
            return _result(
                Observation.API_ITEM_NOT_RETURNED,
                observed_at=observed_at,
                source_status_code=source_status_code,
                expected_content_id_match=False,
                reason="ITEM_NOT_RETURNED_NO_BUSINESS_MEANING",
            )

        for item in items:
            if not isinstance(item, Mapping) or set(item) != _ITEM_FIELDS:
                return _result(
                    Observation.MALFORMED_RESPONSE,
                    observed_at=observed_at,
                    source_status_code=source_status_code,
                    reason="INVALID_ITEM_FIELDS",
                )
            content_id = item["content_id"]
            affiliate = item["affiliate_link_present"]
            if (
                not isinstance(content_id, str)
                or not _CONTENT_ID_RE.fullmatch(content_id)
                or affiliate not in (True, False, None)
                or not (isinstance(affiliate, bool) or affiliate is None)
            ):
                return _result(
                    Observation.MALFORMED_RESPONSE,
                    observed_at=observed_at,
                    source_status_code=source_status_code,
                    reason="INVALID_ITEM_OBSERVATION",
                )

        if len(items) > 1:
            return _result(
                Observation.MULTIPLE_ITEMS_RETURNED,
                observed_at=observed_at,
                source_status_code=source_status_code,
                reason="MULTIPLE_ITEMS_OBSERVED",
            )

        item = items[0]
        if item["content_id"] != expected_content_id:
            return _result(
                Observation.CID_MISMATCH,
                observed_at=observed_at,
                source_status_code=source_status_code,
                expected_content_id_match=False,
                reason="RETURNED_CID_MISMATCH",
            )
        return _result(
            Observation.API_ITEM_VISIBLE,
            observed_at=observed_at,
            source_status_code=source_status_code,
            expected_content_id_match=True,
            affiliate_link_observed=item["affiliate_link_present"],
            reason="ITEM_EXACT_MATCH_OBSERVED",
        )
    except Exception:
        return _result(
            Observation.UNKNOWN,
            observed_at=observed_at if isinstance(observed_at, datetime) else None,
            source_status_code=(
                source_status_code if _valid_source_status(source_status_code) else None
            ),
            reason="INTERNAL_EVALUATION_ERROR",
        )


__all__ = [
    "ErrorClass",
    "Observation",
    "VerificationObservation",
    "evaluate_product_verification",
]
