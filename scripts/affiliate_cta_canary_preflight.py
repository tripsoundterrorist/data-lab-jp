"""One-shot, read-only CTA canary preflight with no default live capability."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
import re
from typing import Any, Callable, Mapping

import affiliate_cta_canary_plan
import affiliate_cta_canary_selection
from product_verification import Observation, evaluate_product_verification


VERSION = "0.1"
READY = "CTA_CANARY_PREFLIGHT_READY_FOR_EXACT_REVIEW"
BLOCKED = "CTA_CANARY_PREFLIGHT_BLOCKED"
FAIL_CLOSED = "CTA_CANARY_PREFLIGHT_FAIL_CLOSED"
PUBLIC_ID = re.compile(r"itm_[0-9a-f]{24}\Z")
CONTENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")


@dataclass(frozen=True)
class AffiliateCtaCanaryPreflight:
    version: str
    status: str
    submitted_count: int
    lookup_attempt_count: int
    api_request_attempt_count: int
    verified_count: int
    selected_count: int
    rate_limit_stop: bool
    identifiers_exposed: bool
    network_capability_present: bool
    production_write_performed: bool
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
    lookups: int = 0,
    requests: int = 0,
    verified: int = 0,
    selected: int = 0,
    rate_limit_stop: bool = False,
    capability: bool = False,
    reasons: tuple[str, ...],
) -> AffiliateCtaCanaryPreflight:
    return AffiliateCtaCanaryPreflight(
        VERSION, status, submitted, lookups, requests, verified, selected,
        rate_limit_stop, False, capability, False, False, False, False,
        "REVIEW_EXACT_SANITIZED_CANARY_PREFLIGHT" if status == READY
        else "KEEP_AFFILIATE_GATE_CLOSED",
        tuple(sorted(set(reasons))),
    )


def run_preflight(
    public_ids: Any,
    *,
    as_of: Any,
    execution_authorized: Any,
    one_shot: Any,
    resolve_content_id: Any,
    fetch_sanitized_item_payload: Any,
    plan: Any,
) -> AffiliateCtaCanaryPreflight:
    """Run a bounded read-only check and return counts only."""
    submitted = len(public_ids) if type(public_ids) is tuple else 0
    capability = callable(resolve_content_id) and callable(fetch_sanitized_item_payload)
    if execution_authorized is not True or one_shot is not True:
        return _result(
            BLOCKED, submitted=submitted, capability=capability,
            reasons=("EXPLICIT_ONE_SHOT_EXECUTION_APPROVAL_REQUIRED",),
        )
    try:
        if (
            not isinstance(as_of, datetime)
            or as_of.tzinfo is None
            or type(public_ids) is not tuple
            or not 1 <= len(public_ids) <= affiliate_cta_canary_selection.MAX_ITEMS
            or any(type(value) is not str or PUBLIC_ID.fullmatch(value) is None for value in public_ids)
            or len(set(public_ids)) != len(public_ids)
            or not capability
            or not isinstance(plan, affiliate_cta_canary_plan.AffiliateCtaCanaryPlan)
            or plan.status != affiliate_cta_canary_plan.READY
        ):
            return _result(
                BLOCKED, submitted=submitted, capability=capability,
                reasons=("PREFLIGHT_INPUT_INVALID",),
            )

        candidates: list[affiliate_cta_canary_selection.CandidateObservation] = []
        lookups = 0
        requests = 0
        for public_id in public_ids:
            lookups += 1
            try:
                content_id = resolve_content_id(public_id)
            except Exception:
                return _result(
                    FAIL_CLOSED, submitted=submitted, lookups=lookups,
                    requests=requests, capability=True,
                    reasons=("PRIVATE_ITEM_LOOKUP_FAILED",),
                )
            if type(content_id) is not str or CONTENT_ID.fullmatch(content_id) is None:
                return _result(
                    BLOCKED, submitted=submitted, lookups=lookups,
                    requests=requests, capability=True,
                    reasons=("PRIVATE_ITEM_NOT_RESOLVED",),
                )
            requests += 1
            try:
                payload = fetch_sanitized_item_payload(content_id)
            except Exception:
                return _result(
                    FAIL_CLOSED, submitted=submitted, lookups=lookups,
                    requests=requests, capability=True,
                    reasons=("API_REQUEST_FAILED",),
                )
            if not isinstance(payload, Mapping):
                return _result(
                    BLOCKED, submitted=submitted, lookups=lookups,
                    requests=requests, capability=True,
                    reasons=("SANITIZED_API_PAYLOAD_INVALID",),
                )
            observation = evaluate_product_verification(payload, as_of=as_of)
            if observation.observation is Observation.API_RATE_LIMITED:
                return _result(
                    BLOCKED, submitted=submitted, lookups=lookups,
                    requests=requests, rate_limit_stop=True, capability=True,
                    reasons=("RATE_LIMIT_STOPPED_REMAINING_REQUESTS",),
                )
            candidates.append(
                affiliate_cta_canary_selection.CandidateObservation(
                    public_id=public_id, verification=observation
                )
            )

        selected = affiliate_cta_canary_selection.select(
            tuple(candidates), as_of=as_of, plan=plan
        )
        if selected.status != affiliate_cta_canary_selection.READY:
            return _result(
                BLOCKED, submitted=submitted, lookups=lookups,
                requests=requests, verified=selected.eligible_count,
                capability=True, reasons=selected.reason_codes,
            )
        return _result(
            READY, submitted=submitted, lookups=lookups, requests=requests,
            verified=selected.eligible_count, selected=selected.selected_count,
            capability=True,
            reasons=(
                "ALL_REQUESTED_ITEMS_VERIFIED",
                "SANITIZED_COUNTS_ONLY",
                "NO_PRODUCTION_MUTATION_PERFORMED",
                "EXACT_SELECTION_AND_ACTIVATION_APPROVAL_REQUIRED",
            ),
        )
    except Exception:
        return _result(
            FAIL_CLOSED, submitted=submitted, capability=capability,
            reasons=("CTA_CANARY_PREFLIGHT_INTERNAL_ERROR",),
        )


def main() -> int:
    result = run_preflight(
        (), as_of=None, execution_authorized=False, one_shot=False,
        resolve_content_id=None, fetch_sanitized_item_payload=None,
        plan=None,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

