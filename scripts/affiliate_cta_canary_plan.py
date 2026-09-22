"""Pure, non-activating review plan for a first affiliate CTA canary."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

import affiliate_cta_presentation
import revenue_mvp_current_state


VERSION = "0.1"
READY = "CTA_CANARY_READY_FOR_COMPLIANCE_REVIEW"
BLOCKED = "CTA_CANARY_PLAN_BLOCKED"
CTA_LABEL = affiliate_cta_presentation.CTA_LABEL
DISCLOSURE_TEXT = affiliate_cta_presentation.DISCLOSURE_TEXT
MAX_INITIAL_ITEMS = 10
REQUIRED_METRICS = (
    "cta_impressions", "cta_clicks", "redirect_successes",
    "redirect_blocks", "ctr",
)
STOP_CONDITIONS = (
    "EDGE_ARTIFACT_MISMATCH",
    "PR_DISCLOSURE_MISSING_OR_NOT_PROXIMATE",
    "AFFILIATE_ELIGIBILITY_UNVERIFIED",
    "TARGET_OR_LIFECYCLE_REVALIDATION_FAILED",
    "DUPLICATE_OR_UNATTRIBUTABLE_EVENT",
    "REDIRECT_ERROR_RATE_ABOVE_REVIEWED_THRESHOLD",
)


@dataclass(frozen=True)
class AffiliateCtaCanaryPlan:
    version: str
    status: str
    proposed_item_limit: int
    cta_label: str | None
    disclosure_text: str | None
    placement: str | None
    required_metrics: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    compliance_approval_required: bool
    user_activation_approval_required: bool
    cta_activation_allowed: bool
    d1_write_allowed: bool
    deployment_allowed: bool
    paid_plan_change_allowed: bool
    next_action: str
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("required_metrics", "stop_conditions", "reason_codes"):
            value[key] = list(value[key])
        return value


def _blocked(reason: str) -> AffiliateCtaCanaryPlan:
    return AffiliateCtaCanaryPlan(
        VERSION, BLOCKED, 0, None, None, None, (), (), True, True,
        False, False, False, False, "RECONCILE_CTA_CANARY_INPUT", (reason,),
    )


def assess(current: Any, proposed_item_limit: Any = MAX_INITIAL_ITEMS) -> AffiliateCtaCanaryPlan:
    """Prepare review facts only; this function can never authorize activation."""
    try:
        if type(proposed_item_limit) is not int or not 1 <= proposed_item_limit <= MAX_INITIAL_ITEMS:
            return _blocked("INITIAL_CANARY_LIMIT_INVALID")
        if (
            not isinstance(current, revenue_mvp_current_state.CurrentRevenueState)
            or current.status != revenue_mvp_current_state.LIVE_AFFILIATE_CLOSED
            or current.limited_surface_live is not True
            or current.edge_artifact_verified is not True
            or current.affiliate_runtime_candidate_ready is not True
            or current.affiliate_d1_lookup_ready is not True
            or current.affiliate_d1_enabled_row_count != 0
            or current.cta_allowed is not False
            or current.affiliate_integration_allowed is not False
            or current.production_write_allowed is not False
            or current.paid_plan_change_allowed is not False
        ):
            return _blocked("CURRENT_REVENUE_STATE_NOT_SAFE_FOR_CTA_REVIEW")
        return AffiliateCtaCanaryPlan(
            VERSION, READY, proposed_item_limit, CTA_LABEL, DISCLOSURE_TEXT,
            "WITHIN_SAME_ITEM_CARD_IMMEDIATELY_BEFORE_CTA",
            REQUIRED_METRICS, STOP_CONDITIONS, True, True,
            False, False, False, False,
            "OBTAIN_COMPLIANCE_DECISION_FOR_EXACT_CANARY_CONTRACT",
            (
                "CURRENT_LIMITED_SURFACE_VERIFIED_LIVE",
                "INITIAL_SCOPE_CAPPED_AT_TEN_ITEMS",
                "PR_DISCLOSURE_AND_CTA_CO_PRESENTATION_REQUIRED",
                "SAME_ORIGIN_OPAQUE_GO_ROUTE_REQUIRED",
                "NO_ACTIVATION_AUTHORITY_GRANTED",
            ),
        )
    except Exception:
        return _blocked("CTA_CANARY_PLAN_INTERNAL_ERROR")


def current_plan() -> AffiliateCtaCanaryPlan:
    return assess(revenue_mvp_current_state.current_state())


def main() -> int:
    result = current_plan()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())

