"""Pure, fail-closed contract for an unordered reduced-surface manual review."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from revenue_mvp_official_lifecycle_policy import (
    EligibilityState,
    OfficialLifecycleDecision,
)


CONTRACT_VERSION = "0.1"
REVIEW_CANDIDATE = "UNORDERED_SURFACE_REVIEW_CANDIDATE"
BLOCKED = "UNORDERED_SURFACE_REVIEW_BLOCKED"
INVALID_INPUT = "UNORDERED_SURFACE_INVALID_INPUT"
PRESENTATION_MODE = "UNORDERED_GRID"
TIMESTAMP_LABEL = "API取得確認時刻"
TRANSPARENCY_NOTICE = (
    "表示内容は、各項目を確認できた時点の記録です。"
    "順位・並び順・更新頻度・在庫・販売状況を示すものではありません。"
)
ALLOWED_PUBLIC_FIELDS = frozenset(
    {"title", "current_price", "price_observed_at", "api_observed_at", "transparency_notice"}
)
REQUIRED_PUBLIC_FIELDS = frozenset({"title", "api_observed_at", "transparency_notice"})
PRICE_FIELDS = frozenset({"current_price", "price_observed_at"})
FORBIDDEN_PUBLIC_FIELDS = frozenset(
    {
        "affiliate_cta", "affiliate_disclosure", "affiliate_url", "availability",
        "content_id", "first_position", "history", "inventory", "offset", "ordinal",
        "price_history", "provider_updated_at", "rank", "rank_number", "review",
        "review_average", "review_count", "sale_end_reason", "sort_label",
        "source_position", "source_sort", "stock", "update_frequency",
    }
)
REQUIRED_CLAIM_CODES = frozenset({"API_OBSERVED_AT", "UNORDERED_PRESENTATION"})
PRICE_CLAIM_CODE = "PRICE_OBSERVED_AT"
FORBIDDEN_CLAIM_CODES = frozenset(
    {
        "AFFILIATE_CTA", "API_FETCH_ORDER", "AVAILABILITY", "HISTORY", "LATEST",
        "OFFSET", "ORDINAL", "RANK", "REALTIME", "REVIEW_ORDER", "SALE_STATUS",
        "SOURCE_SORT", "TOP_N", "UPDATE_CADENCE",
    }
)


@dataclass(frozen=True)
class UnorderedSurfaceReview:
    status: str
    eligible_for_manual_gate_review: bool
    publication_allowed: bool
    production_activation_allowed: bool
    affiliate_eligibility_allowed: bool
    gate_mutation_allowed: bool
    cta_allowed: bool
    api_order_label_allowed: bool
    price_display_allowed: bool
    required_public_fields: tuple[str, ...]
    timestamp_label: str
    transparency_notice: str
    reason_codes: tuple[str, ...]


def _blocked(status: str, *reasons: str) -> UnorderedSurfaceReview:
    return UnorderedSurfaceReview(
        status=status,
        eligible_for_manual_gate_review=False,
        publication_allowed=False,
        production_activation_allowed=False,
        affiliate_eligibility_allowed=False,
        gate_mutation_allowed=False,
        cta_allowed=False,
        api_order_label_allowed=False,
        price_display_allowed=False,
        required_public_fields=(),
        timestamp_label=TIMESTAMP_LABEL,
        transparency_notice=TRANSPARENCY_NOTICE,
        reason_codes=reasons,
    )


def _is_aware(value: Any) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None


def _exact_string_set(value: Any) -> frozenset[str] | None:
    if type(value) not in {set, frozenset, tuple, list}:
        return None
    if any(type(item) is not str or not item for item in value):
        return None
    return frozenset(value)


def review_unordered_surface(
    lifecycle_decision: Any,
    *,
    contract_version: Any,
    lifecycle_freshness_confirmed: Any,
    api_observed_at: Any,
    public_fields: Any,
    public_claim_codes: Any,
    presentation_mode: Any,
    sort_controls_present: Any,
    position_indicators_present: Any,
    history_present: Any,
    affiliate_cta_requested: Any,
    title_snapshot_provenance_confirmed: Any,
    transparency_notice: Any,
    price_observed_at: Any = None,
) -> UnorderedSurfaceReview:
    """Return a manual-review candidate only when every bounded condition holds."""
    try:
        if contract_version != CONTRACT_VERSION:
            return _blocked(INVALID_INPUT, "CONTRACT_VERSION_INVALID")
        if type(lifecycle_decision) is not OfficialLifecycleDecision:
            return _blocked(INVALID_INPUT, "LIFECYCLE_DECISION_INVALID")
        if type(lifecycle_freshness_confirmed) is not bool:
            return _blocked(INVALID_INPUT, "LIFECYCLE_FRESHNESS_INVALID")
        if not lifecycle_freshness_confirmed:
            return _blocked(BLOCKED, "LIFECYCLE_FRESHNESS_NOT_CONFIRMED")
        if (
            lifecycle_decision.state is not EligibilityState.CANDIDATE
            or not lifecycle_decision.public_listing_candidate
            or not lifecycle_decision.affiliate_candidate
            or lifecycle_decision.exclude_from_public_site
            or lifecycle_decision.publication_gate_change_allowed
            or lifecycle_decision.public_rank_number_allowed
            or lifecycle_decision.offset_rank_allowed
            or lifecycle_decision.update_frequency_claim_allowed
            or lifecycle_decision.internal_history_retention_allowed
        ):
            return _blocked(BLOCKED, "LIFECYCLE_NOT_REVIEW_ELIGIBLE")
        if (
            not _is_aware(lifecycle_decision.observation_observed_at)
            or not _is_aware(api_observed_at)
            or api_observed_at != lifecycle_decision.observation_observed_at
        ):
            return _blocked(BLOCKED, "API_OBSERVATION_PROVENANCE_INVALID")
        if type(title_snapshot_provenance_confirmed) is not bool:
            return _blocked(INVALID_INPUT, "TITLE_PROVENANCE_INVALID")
        if not title_snapshot_provenance_confirmed:
            return _blocked(BLOCKED, "TITLE_SNAPSHOT_PROVENANCE_NOT_CONFIRMED")
        fields = _exact_string_set(public_fields)
        claims = _exact_string_set(public_claim_codes)
        if fields is None or claims is None:
            return _blocked(INVALID_INPUT, "DISPLAY_CONTRACT_INVALID")
        if not REQUIRED_PUBLIC_FIELDS.issubset(fields):
            return _blocked(BLOCKED, "REQUIRED_DISPLAY_FIELD_MISSING")
        if not fields.issubset(ALLOWED_PUBLIC_FIELDS) or fields & FORBIDDEN_PUBLIC_FIELDS:
            return _blocked(BLOCKED, "FORBIDDEN_DISPLAY_FIELD_REQUESTED")
        has_price = bool(fields & PRICE_FIELDS)
        if has_price and fields & PRICE_FIELDS != PRICE_FIELDS:
            return _blocked(BLOCKED, "PRICE_PROVENANCE_FIELD_INCOMPLETE")
        if has_price and (
            not _is_aware(price_observed_at) or price_observed_at != api_observed_at
        ):
            return _blocked(BLOCKED, "PRICE_OBSERVATION_PROVENANCE_INVALID")
        if not has_price and price_observed_at is not None:
            return _blocked(BLOCKED, "UNREQUESTED_PRICE_OBSERVATION_PRESENT")
        expected_claims = REQUIRED_CLAIM_CODES | (
            frozenset({PRICE_CLAIM_CODE}) if has_price else frozenset()
        )
        if claims != expected_claims or claims & FORBIDDEN_CLAIM_CODES:
            return _blocked(BLOCKED, "PUBLIC_CLAIM_NOT_ALLOWED")
        if (
            presentation_mode != PRESENTATION_MODE
            or type(sort_controls_present) is not bool
            or type(position_indicators_present) is not bool
            or type(history_present) is not bool
            or type(affiliate_cta_requested) is not bool
            or sort_controls_present
            or position_indicators_present
            or history_present
            or affiliate_cta_requested
        ):
            return _blocked(BLOCKED, "ORDER_OR_CTA_PRESENTATION_NOT_ALLOWED")
        if transparency_notice != TRANSPARENCY_NOTICE:
            return _blocked(BLOCKED, "TRANSPARENCY_NOTICE_INVALID")
        return UnorderedSurfaceReview(
            status=REVIEW_CANDIDATE,
            eligible_for_manual_gate_review=True,
            publication_allowed=False,
            production_activation_allowed=False,
            affiliate_eligibility_allowed=False,
            gate_mutation_allowed=False,
            cta_allowed=False,
            api_order_label_allowed=False,
            price_display_allowed=has_price,
            required_public_fields=tuple(sorted(REQUIRED_PUBLIC_FIELDS)),
            timestamp_label=TIMESTAMP_LABEL,
            transparency_notice=TRANSPARENCY_NOTICE,
            reason_codes=(
                "UNORDERED_REDUCED_SURFACE_ONLY",
                "MANUAL_GATE_REVIEW_REQUIRED",
                "PUBLICATION_PERMISSION_NOT_GRANTED",
            ),
        )
    except Exception:
        return _blocked(INVALID_INPUT, "UNORDERED_SURFACE_REVIEW_ERROR")


__all__ = [
    "ALLOWED_PUBLIC_FIELDS", "BLOCKED", "CONTRACT_VERSION", "FORBIDDEN_CLAIM_CODES",
    "FORBIDDEN_PUBLIC_FIELDS", "INVALID_INPUT", "PRESENTATION_MODE",
    "PRICE_CLAIM_CODE", "REQUIRED_CLAIM_CODES", "REQUIRED_PUBLIC_FIELDS",
    "REVIEW_CANDIDATE", "TIMESTAMP_LABEL", "TRANSPARENCY_NOTICE",
    "UnorderedSurfaceReview", "review_unordered_surface",
]
