"""Pure fail-closed candidate policy for ebook comic review pairs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any


VERSION = "0.1"
READY = "READY_FOR_NON_PUBLIC_PROJECTION_DESIGN"
FAIL_CLOSED = "FAIL_CLOSED"
PRESERVE_COMPLETE = "PRESERVE_COMPLETE_PAIR"
OMIT_ABSENT = "OMIT_ABSENT_PAIR"
OMIT_INCOMPLETE = "OMIT_INCOMPLETE_PAIR"
BLOCK_INVALID = "BLOCK_INVALID_PAIR"


@dataclass(frozen=True)
class EbookComicReviewPairPolicyCandidate:
    version: str
    status: str
    source_state: str
    projection_action: str
    source_history_mutation_allowed: bool
    inferred_value_allowed: bool
    compliance_approved: bool
    publication_allowed: bool
    production_write_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["reason_codes"] = list(self.reason_codes)
        return result


def _valid_average(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and value >= 0
    )


def _valid_count(value: Any) -> bool:
    return type(value) is int and value >= 0


def _result(
    *,
    status: str,
    source_state: str,
    action: str,
    reasons: tuple[str, ...],
) -> EbookComicReviewPairPolicyCandidate:
    return EbookComicReviewPairPolicyCandidate(
        VERSION,
        status,
        source_state,
        action,
        False,
        False,
        False,
        False,
        False,
        reasons,
    )


def assess(average: Any, count: Any) -> EbookComicReviewPairPolicyCandidate:
    if average is None and count is None:
        return _result(
            status=READY,
            source_state="ABSENT",
            action=OMIT_ABSENT,
            reasons=(
                "REVIEW_PAIR_ABSENT",
                "NO_VALUE_INFERENCE_ALLOWED",
                "PUBLICATION_REMAINS_CLOSED",
            ),
        )
    if average is None or count is None:
        present_value = count if average is None else average
        valid_present_value = (
            _valid_count(present_value)
            if average is None
            else _valid_average(present_value)
        )
        if not valid_present_value:
            return _result(
                status=FAIL_CLOSED,
                source_state="INVALID",
                action=BLOCK_INVALID,
                reasons=("REVIEW_PAIR_VALUE_INVALID",),
            )
        return _result(
            status=READY,
            source_state="INCOMPLETE",
            action=OMIT_INCOMPLETE,
            reasons=(
                "REVIEW_PAIR_INCOMPLETE",
                "SOURCE_HISTORY_PRESERVED",
                "NO_VALUE_INFERENCE_ALLOWED",
                "PUBLICATION_REMAINS_CLOSED",
            ),
        )
    if not (_valid_average(average) and _valid_count(count)):
        return _result(
            status=FAIL_CLOSED,
            source_state="INVALID",
            action=BLOCK_INVALID,
            reasons=("REVIEW_PAIR_VALUE_INVALID",),
        )
    return _result(
        status=READY,
        source_state="COMPLETE",
        action=PRESERVE_COMPLETE,
        reasons=(
            "REVIEW_PAIR_COMPLETE",
            "DISPLAY_RIGHTS_AND_SEMANTICS_REVIEW_REQUIRED",
            "PUBLICATION_REMAINS_CLOSED",
        ),
    )
