"""Pure fail-closed review for the reduced Revenue MVP public surface."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import inspect
from typing import Any

from revenue_mvp_official_lifecycle_policy import (
    EligibilityState,
    OfficialLifecycleDecision,
)


CONTRACT_VERSION = "0.1"
REVIEW_CANDIDATE = "REVIEW_CANDIDATE"
BLOCKED = "BLOCKED"
INVALID_INPUT = "INVALID_INPUT"

SORT_LABELS = {
    "rank": "DMM API（sort=rank）取得時の並び順",
    "review": "DMM API（sort=review）取得時の並び順",
}
TIMESTAMP_LABEL = "API取得日時"
ALLOWED_PUBLIC_SEMANTIC_FIELDS = frozenset({
    "api_observed_at",
    "sort_label",
    "affiliate_cta",
    "affiliate_disclosure",
})
FORBIDDEN_PUBLIC_FIELDS = frozenset({
    "rank",
    "rank_number",
    "ordinal",
    "offset",
    "first_position",
    "source_position",
    "update_frequency",
    "provider_updated_at",
})
ALLOWED_CLAIMS = frozenset({"API_FETCH_ORDER", "API_OBSERVED_AT"})
FORBIDDEN_CLAIMS = frozenset({
    "ORDINAL_RANK",
    "TOP_N",
    "OFFSET_DERIVED_RANK",
    "POSITION_DERIVED_RANK",
    "RANK_HISTORY",
    "UPDATE_FREQUENCY",
    "REALTIME",
    "LATEST",
    "AVAILABLE_FOR_PURCHASE",
    "IN_STOCK",
})


@dataclass(frozen=True)
class ReducedSurfaceReview:
    contract_version: str
    status: str
    surface_contract_satisfied: bool
    gate_review_candidate: bool
    allowed_sort_label: str | None
    timestamp_label: str | None
    cta_candidate: bool
    publication_gate_change_allowed: bool
    production_publication_allowed: bool
    external_send_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(
    status: str,
    *,
    satisfied: bool = False,
    label: str | None = None,
    cta: bool = False,
    reasons: tuple[str, ...],
) -> ReducedSurfaceReview:
    return ReducedSurfaceReview(
        CONTRACT_VERSION,
        status,
        satisfied,
        satisfied,
        label if satisfied else None,
        TIMESTAMP_LABEL if satisfied else None,
        cta if satisfied else False,
        False,
        False,
        False,
        tuple(sorted(set(reasons))),
    )


def _valid_lifecycle(value: Any) -> bool:
    return (
        type(value) is OfficialLifecycleDecision
        and value.state is EligibilityState.CANDIDATE
        and value.public_listing_candidate is True
        and value.affiliate_candidate is True
        and value.exclude_from_public_site is False
        and value.public_rank_number_allowed is False
        and value.offset_rank_allowed is False
        and value.update_frequency_claim_allowed is False
        and value.internal_history_retention_allowed is False
        and value.publication_gate_change_allowed is False
    )


def review_reduced_surface(
    *,
    contract_version: Any,
    lifecycle_decision: Any,
    source_sort: Any,
    public_order_matches_api: Any,
    api_observed_at: Any,
    requested_sort_label: Any,
    timestamp_label: Any,
    public_semantic_fields: Any,
    public_claim_codes: Any,
    affiliate_url_validated: Any,
    cta_requested: Any,
    disclosure_visible: Any,
    disclosure_proximate: Any,
) -> ReducedSurfaceReview:
    """Return review eligibility only; never unlock or publish anything."""

    try:
        if contract_version != CONTRACT_VERSION:
            return _result(INVALID_INPUT, reasons=("CONTRACT_VERSION_UNSUPPORTED",))
        boolean_values = (
            public_order_matches_api,
            affiliate_url_validated,
            cta_requested,
            disclosure_visible,
            disclosure_proximate,
        )
        if any(type(value) is not bool for value in boolean_values):
            return _result(INVALID_INPUT, reasons=("BOOLEAN_INPUT_INVALID",))
        if source_sort not in SORT_LABELS:
            return _result(INVALID_INPUT, reasons=("SOURCE_SORT_UNSUPPORTED",))
        if requested_sort_label != SORT_LABELS[source_sort]:
            return _result(BLOCKED, reasons=("SORT_LABEL_NOT_ALLOWLISTED",))
        if timestamp_label != TIMESTAMP_LABEL:
            return _result(BLOCKED, reasons=("TIMESTAMP_LABEL_NOT_ALLOWLISTED",))
        if (
            not isinstance(api_observed_at, datetime)
            or api_observed_at.tzinfo is None
            or api_observed_at.utcoffset() is None
        ):
            return _result(INVALID_INPUT, reasons=("API_OBSERVED_AT_INVALID",))
        if not isinstance(public_semantic_fields, (tuple, list, set, frozenset)):
            return _result(INVALID_INPUT, reasons=("PUBLIC_FIELDS_INVALID",))
        if not isinstance(public_claim_codes, (tuple, list, set, frozenset)):
            return _result(INVALID_INPUT, reasons=("PUBLIC_CLAIMS_INVALID",))
        fields = frozenset(public_semantic_fields)
        claims = frozenset(public_claim_codes)
        if any(type(value) is not str or not value for value in fields | claims):
            return _result(INVALID_INPUT, reasons=("PUBLIC_SEMANTICS_INVALID",))

        reasons: list[str] = []
        if not _valid_lifecycle(lifecycle_decision):
            reasons.append("LIFECYCLE_CANDIDATE_REQUIRED")
        if public_order_matches_api is not True:
            reasons.append("API_ORDER_NOT_PRESERVED")
        if fields - ALLOWED_PUBLIC_SEMANTIC_FIELDS:
            reasons.append("PUBLIC_FIELD_NOT_ALLOWLISTED")
        if fields & FORBIDDEN_PUBLIC_FIELDS:
            reasons.append("FORBIDDEN_PUBLIC_FIELD")
        if claims - ALLOWED_CLAIMS:
            reasons.append("PUBLIC_CLAIM_NOT_ALLOWLISTED")
        if claims & FORBIDDEN_CLAIMS:
            reasons.append("FORBIDDEN_PUBLIC_CLAIM")
        if not {"api_observed_at", "sort_label"} <= fields:
            reasons.append("REQUIRED_PUBLIC_SEMANTICS_MISSING")
        if claims != ALLOWED_CLAIMS:
            reasons.append("REQUIRED_PUBLIC_CLAIMS_MISSING")
        if affiliate_url_validated is not True:
            reasons.append("AFFILIATE_URL_VALIDATION_REQUIRED")
        if cta_requested is not True:
            reasons.append("AFFILIATE_CTA_REQUIRED")
        if not {"affiliate_cta", "affiliate_disclosure"} <= fields:
            reasons.append("AFFILIATE_SURFACE_FIELDS_MISSING")
        if disclosure_visible is not True or disclosure_proximate is not True:
            reasons.append("PROXIMATE_DISCLOSURE_REQUIRED")
        if reasons:
            return _result(BLOCKED, reasons=tuple(reasons))
        return _result(
            REVIEW_CANDIDATE,
            satisfied=True,
            label=SORT_LABELS[source_sort],
            cta=True,
            reasons=(
                "REDUCED_SURFACE_CONTRACT_SATISFIED",
                "SEPARATE_GATE_REVIEW_REQUIRED",
                "PUBLICATION_REMAINS_FORBIDDEN",
            ),
        )
    except Exception:
        return _result(INVALID_INPUT, reasons=("REDUCED_SURFACE_REVIEW_ERROR",))


def accepted_input_names() -> tuple[str, ...]:
    """Expose the bounded input contract for regression tests and reviewers."""

    return tuple(inspect.signature(review_reduced_surface).parameters)


__all__ = [
    "ALLOWED_CLAIMS",
    "ALLOWED_PUBLIC_SEMANTIC_FIELDS",
    "BLOCKED",
    "CONTRACT_VERSION",
    "FORBIDDEN_CLAIMS",
    "FORBIDDEN_PUBLIC_FIELDS",
    "INVALID_INPUT",
    "REVIEW_CANDIDATE",
    "ReducedSurfaceReview",
    "SORT_LABELS",
    "TIMESTAMP_LABEL",
    "accepted_input_names",
    "review_reduced_surface",
]
