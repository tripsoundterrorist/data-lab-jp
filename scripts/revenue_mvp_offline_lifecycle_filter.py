"""Isolated lifecycle filter before the offline publication artifact builder."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import re
from typing import Any

import publication_gate
import revenue_mvp_official_lifecycle_policy as lifecycle


VERSION = "0.1-candidate"
INCLUDE_CANDIDATE = "OFFLINE_ARTIFACT_INCLUDE_CANDIDATE"
EXCLUDED = "OFFLINE_ARTIFACT_EXCLUDED"
FAIL_CLOSED = "OFFLINE_ARTIFACT_FAIL_CLOSED"
PROHIBITED_ARTIFACT_FIELDS = frozenset({
    "first_position", "source_position", "source_offset", "offset", "rank",
    "ranking", "top",
})
_PROHIBITED_NORMALIZED_FIELDS = frozenset(
    re.sub(r"[^a-z0-9]", "", value) for value in PROHIBITED_ARTIFACT_FIELDS
)


@dataclass(frozen=True)
class OfflineCtaEvidence:
    same_item: bool
    same_observation: bool
    affiliate_url_validated: bool
    pr_disclosure_present: bool


@dataclass(frozen=True)
class OfflineLifecycleFilterResult:
    version: str
    status: str
    include_in_offline_artifact: bool
    affiliate_cta_candidate: bool
    production_cta_allowed: bool
    publication_allowed: bool
    observation_timestamp_allowed: bool
    latestness_claim_allowed: bool
    public_rank_allowed: bool
    source_position_allowed: bool
    update_frequency_claim_allowed: bool
    api_order_label_allowed: bool
    observation_observed_at: str | None
    index_detail_filter_required: bool
    lifecycle_state: str | None
    lifecycle_reason_codes: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["lifecycle_reason_codes"] = list(self.lifecycle_reason_codes)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(
    status: str,
    *,
    include: bool = False,
    cta: bool = False,
    timestamp: bool = False,
    observed_at: str | None = None,
    api_order_label: bool = False,
    decision: lifecycle.OfficialLifecycleDecision | None = None,
    reasons: tuple[str, ...],
) -> OfflineLifecycleFilterResult:
    return OfflineLifecycleFilterResult(
        VERSION,
        status,
        include,
        cta,
        False,
        False,
        timestamp,
        False,
        False,
        False,
        False,
        api_order_label,
        observed_at,
        True,
        decision.state.value if decision is not None else None,
        decision.reason_codes if decision is not None else (),
        reasons,
    )


def _publication_gate_passed(value: publication_gate.PublicationGateResult) -> bool:
    return (
        value.gate_version == publication_gate.GATE_VERSION
        and value.overall_eligible is True
        and value.publication_status == "public"
        and value.rights_gate == publication_gate.PASS
        and value.lifecycle_gate == publication_gate.PASS
        and value.semantics_gate == publication_gate.PASS
        and value.publication_status_gate == publication_gate.PASS
        and value.data_policy_gate == publication_gate.PASS
    )


def _artifact_fields_allowed(value: Any) -> bool:
    return (
        type(value) is tuple
        and bool(value)
        and all(type(field) is str and field for field in value)
        and len(value) == len(set(value))
        and not any(
            re.sub(r"[^a-z0-9]", "", field.casefold())
            in _PROHIBITED_NORMALIZED_FIELDS
            for field in value
        )
    )


def filter_offline_artifact_candidate(
    decision: Any,
    gate: Any,
    *,
    freshness_confirmed: Any,
    api_order_preserved: Any,
    index_field_names: Any,
    detail_field_names: Any,
    cta_evidence: Any = None,
) -> OfflineLifecycleFilterResult:
    """Filter one candidate in memory; never builds or writes an artifact."""

    try:
        if type(decision) is not lifecycle.OfficialLifecycleDecision:
            return _result(
                FAIL_CLOSED, reasons=("LIFECYCLE_DECISION_INVALID",)
            )
        if type(gate) is not publication_gate.PublicationGateResult:
            return _result(FAIL_CLOSED, reasons=("PUBLICATION_GATE_INVALID",))
        if type(freshness_confirmed) is not bool or type(api_order_preserved) is not bool:
            return _result(FAIL_CLOSED, reasons=("FRESHNESS_EVIDENCE_INVALID",))
        if not _artifact_fields_allowed(index_field_names) or not _artifact_fields_allowed(
            detail_field_names
        ):
            return _result(
                FAIL_CLOSED, reasons=("PROHIBITED_OR_INVALID_ARTIFACT_FIELDS",)
            )

        if decision.version != lifecycle.POLICY_VERSION:
            return _result(
                FAIL_CLOSED, reasons=("LIFECYCLE_POLICY_VERSION_INVALID",)
            )
        if (
            decision.publication_gate_change_allowed is not False
            or decision.public_rank_number_allowed is not False
            or decision.offset_rank_allowed is not False
            or decision.update_frequency_claim_allowed is not False
        ):
            return _result(
                FAIL_CLOSED, decision=decision,
                reasons=("LIFECYCLE_DECISION_PERMISSIVE",)
            )

        if decision.state is not lifecycle.EligibilityState.CANDIDATE:
            return _result(
                EXCLUDED,
                decision=decision,
                reasons=("LIFECYCLE_NOT_ELIGIBLE", "REMOVED_FROM_ARTIFACT_AND_CTA"),
            )
        if not freshness_confirmed:
            return _result(
                EXCLUDED,
                decision=decision,
                reasons=("FRESHNESS_NOT_CONFIRMED", "NO_LATESTNESS_CLAIM"),
            )
        if (
            not isinstance(decision.observation_observed_at, datetime)
            or decision.observation_observed_at.tzinfo is None
        ):
            return _result(
                FAIL_CLOSED, decision=decision,
                reasons=("LIFECYCLE_OBSERVATION_TIME_INVALID",)
            )
        if not _publication_gate_passed(gate):
            return _result(
                EXCLUDED,
                decision=decision,
                timestamp=True,
                observed_at=decision.observation_observed_at.isoformat(),
                reasons=("PUBLICATION_GATE_NOT_PASSED", "CANDIDATE_ALONE_INSUFFICIENT"),
            )
        cta_ready = (
            type(cta_evidence) is OfflineCtaEvidence
            and cta_evidence.same_item is True
            and cta_evidence.same_observation is True
            and cta_evidence.affiliate_url_validated is True
            and cta_evidence.pr_disclosure_present is True
        )
        return _result(
            INCLUDE_CANDIDATE,
            decision=decision,
            include=True,
            cta=cta_ready,
            timestamp=True,
            observed_at=decision.observation_observed_at.isoformat(),
            api_order_label=api_order_preserved,
            reasons=(
                "OFFLINE_FILTERS_PASSED",
                "CTA_EVIDENCE_VERIFIED" if cta_ready else "CTA_EVIDENCE_INCOMPLETE",
                "API_ORDER_PRESERVED" if api_order_preserved else "API_ORDER_LABEL_SUPPRESSED",
                "PRODUCTION_PUBLICATION_REMAINS_SEPARATE",
            ),
        )
    except Exception:
        return _result(FAIL_CLOSED, reasons=("OFFLINE_FILTER_INTERNAL_ERROR",))


__all__ = [
    "EXCLUDED", "FAIL_CLOSED", "INCLUDE_CANDIDATE",
    "OfflineCtaEvidence", "OfflineLifecycleFilterResult",
    "PROHIBITED_ARTIFACT_FIELDS", "VERSION",
    "filter_offline_artifact_candidate",
]
