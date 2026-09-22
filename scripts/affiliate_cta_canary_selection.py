"""Identifier-free result contract for selecting an initial CTA canary set."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import json
import re
from typing import Any

import affiliate_cta_canary_plan
import revenue_mvp_official_lifecycle_policy as lifecycle
from product_verification import VerificationObservation


VERSION = "0.1"
READY = "CTA_CANARY_SELECTION_READY_FOR_SEPARATE_APPROVAL"
BLOCKED = "CTA_CANARY_SELECTION_BLOCKED"
PUBLIC_ID = re.compile(r"itm_[0-9a-f]{24}\Z")
MAX_ITEMS = affiliate_cta_canary_plan.MAX_INITIAL_ITEMS
MAX_SELECTION_AGE = timedelta(minutes=15)


@dataclass(frozen=True)
class CandidateObservation:
    public_id: str
    verification: VerificationObservation
    inventory_signal: lifecycle.InventorySignal = lifecycle.InventorySignal.UNKNOWN


@dataclass(frozen=True)
class AffiliateCtaCanarySelection:
    version: str
    status: str
    submitted_count: int
    eligible_count: int
    selected_count: int
    click_time_revalidation_required: bool
    static_affiliate_url_allowed: bool
    identifiers_exposed: bool
    cta_activation_allowed: bool
    d1_write_allowed: bool
    deployment_allowed: bool
    next_action: str
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(
    status: str,
    *,
    submitted: int = 0,
    eligible: int = 0,
    selected: int = 0,
    reasons: tuple[str, ...],
) -> AffiliateCtaCanarySelection:
    return AffiliateCtaCanarySelection(
        VERSION, status, submitted, eligible, selected, True, False, False,
        False, False, False,
        "OBTAIN_EXACT_SELECTION_AND_ACTIVATION_APPROVAL" if status == READY
        else "REBUILD_CANARY_SELECTION_FROM_FRESH_API_OBSERVATIONS",
        tuple(sorted(set(reasons))),
    )


def select(
    candidates: Any,
    *,
    as_of: Any,
    plan: Any,
) -> AffiliateCtaCanarySelection:
    """Validate a bounded set and return counts only, never identifiers or URLs."""
    try:
        if (
            not isinstance(as_of, datetime)
            or as_of.tzinfo is None
            or not isinstance(plan, affiliate_cta_canary_plan.AffiliateCtaCanaryPlan)
            or plan.status != affiliate_cta_canary_plan.READY
            or plan.cta_activation_allowed is not False
            or plan.d1_write_allowed is not False
            or plan.deployment_allowed is not False
        ):
            return _result(BLOCKED, reasons=("SELECTION_CONTEXT_INVALID",))
        if type(candidates) is not tuple or not 1 <= len(candidates) <= MAX_ITEMS:
            return _result(BLOCKED, reasons=("CANDIDATE_SET_SIZE_INVALID",))
        if any(type(candidate) is not CandidateObservation for candidate in candidates):
            return _result(BLOCKED, submitted=len(candidates), reasons=("CANDIDATE_CONTRACT_INVALID",))
        public_ids = [candidate.public_id for candidate in candidates]
        if (
            any(PUBLIC_ID.fullmatch(value) is None for value in public_ids)
            or len(set(public_ids)) != len(public_ids)
        ):
            return _result(BLOCKED, submitted=len(candidates), reasons=("OPAQUE_PUBLIC_ID_INVALID_OR_DUPLICATE",))

        reasons: list[str] = []
        eligible = 0
        for candidate in candidates:
            observation = candidate.verification
            if (
                type(observation) is not VerificationObservation
                or not isinstance(observation.observed_at, datetime)
                or observation.observed_at.tzinfo is None
                or observation.observed_at > as_of
                or as_of - observation.observed_at > MAX_SELECTION_AGE
            ):
                reasons.append("API_OBSERVATION_MISSING_OR_STALE")
                continue
            decision = lifecycle.evaluate_official_lifecycle_policy(
                observation, inventory_signal=candidate.inventory_signal
            )
            if (
                decision.state is lifecycle.EligibilityState.CANDIDATE
                and decision.public_listing_candidate is True
                and decision.affiliate_candidate is True
                and decision.exclude_from_public_site is False
                and decision.publication_gate_change_allowed is False
            ):
                eligible += 1
            else:
                reasons.extend(decision.reason_codes)
        if reasons or eligible != len(candidates):
            return _result(
                BLOCKED, submitted=len(candidates), eligible=eligible,
                reasons=tuple(reasons) or ("NOT_ALL_CANDIDATES_ELIGIBLE",),
            )
        return _result(
            READY, submitted=len(candidates), eligible=eligible,
            selected=eligible,
            reasons=(
                "ALL_ITEMS_API_VISIBLE_WITH_AFFILIATE_URL",
                "SELECTION_OBSERVATIONS_WITHIN_INTERNAL_FIFTEEN_MINUTE_BOUND",
                "CLICK_TIME_API_REVALIDATION_REQUIRED",
                "STATIC_AFFILIATE_URL_FORBIDDEN",
                "EXACT_SELECTION_REQUIRES_SEPARATE_APPROVAL",
            ),
        )
    except Exception:
        return _result(BLOCKED, reasons=("CTA_CANARY_SELECTION_INTERNAL_ERROR",))


def main() -> int:
    result = _result(
        BLOCKED,
        reasons=("NO_FRESH_SANITIZED_CANDIDATE_OBSERVATIONS_SUPPLIED",),
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

