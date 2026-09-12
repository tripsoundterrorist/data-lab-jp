"""Fail-closed ordered runbook for Revenue MVP monetization activation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

import affiliate_d1_production_state
import affiliate_runtime_deployment_preflight
import revenue_mvp_official_followup_status
import revenue_mvp_publication_artifact_evidence


VERSION = "0.1"
WAITING = "WAITING_FOR_OFFICIAL_RESPONSE"
FAIL_CLOSED = "FAIL_CLOSED"
ORDERED_STEPS = (
    "INTAKE_AND_CLASSIFY_DMM_RESPONSE",
    "REVIEW_AND_UPDATE_LIFECYCLE_SORT_GATES",
    "REFRESH_AND_VALIDATE_PUBLIC_ARTIFACT",
    "PREPARE_EXACT_D1_ELIGIBILITY_DELTA",
    "REVIEW_PUBLICATION_ACTIVATION",
    "APPLY_APPROVED_D1_ELIGIBILITY_DELTA",
    "DEPLOY_PUBLIC_ARTIFACT_AND_WORKER_RELEASE_FACTS",
    "RUN_POST_DEPLOY_PRODUCTION_SMOKE",
    "VERIFY_FUNNEL_ANALYTICS_AND_AFFILIATE_REDIRECT",
    "RECORD_MONETIZATION_START",
)
ROLLBACK_ORDER = (
    "CLOSE_WORKER_RELEASE_FACTS",
    "DISABLE_AFFILIATE_ELIGIBLE_ROWS",
    "REMOVE_PUBLIC_DATA_ARTIFACT",
    "RUN_BLOCKED_ROUTE_AND_SHELL_SMOKE",
)


@dataclass(frozen=True)
class ActivationRunbook:
    version: str
    status: str
    production_activation_allowed: bool
    current_completed_steps: tuple[str, ...]
    remaining_steps: tuple[str, ...]
    next_step: str | None
    rollback_order: tuple[str, ...]
    d1_row_count: int | None
    d1_runtime_eligible_count: int | None
    public_artifact_item_count: int | None
    paid_plan_change_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("current_completed_steps", "remaining_steps", "rollback_order", "reason_codes"):
            value[key] = list(value[key])
        return value


def build_runbook(
    followup: Any,
    artifact: Any,
    d1: Any,
    deployment: Any,
) -> ActivationRunbook:
    """Build an execution order from bounded summaries; never perform a step."""
    try:
        valid = (
            followup.version == revenue_mvp_official_followup_status.VERSION
            and followup.status
            == revenue_mvp_official_followup_status.SUBMITTED_AWAITING_RESPONSE
            and followup.response_received is False
            and followup.official_semantics_resolved is False
            and followup.gate_unlock_allowed is False
            and artifact.version == revenue_mvp_publication_artifact_evidence.VERSION
            and artifact.status
            == revenue_mvp_publication_artifact_evidence.EVIDENCE_READY
            and artifact.source_db_matches is True
            and artifact.artifact_validation_passed is True
            and artifact.publication_allowed is False
            and artifact.production_write_performed is False
            and artifact.gate_unlock_allowed is False
            and d1.status == affiliate_d1_production_state.READY
            and d1.lookup_ready is True
            and d1.all_rows_disabled is True
            and d1.all_rows_pending is True
            and d1.runtime_eligibility_empty is True
            and d1.cloudflare_write_allowed is False
            and d1.deployment_allowed is False
            and d1.paid_plan_change_allowed is False
            and deployment.status
            == affiliate_runtime_deployment_preflight.READY_FOR_DEPLOYMENT_REVIEW
            and deployment.deployment_candidate is True
            and deployment.production_deployment_allowed is False
        )
        if not valid:
            raise ValueError("activation evidence invalid")
        completed = (
            "VALIDATE_INERT_AFFILIATE_RUNTIME",
            "VALIDATE_CURRENT_PUBLIC_ARTIFACT",
            "SUBMIT_DMM_FOLLOWUP_INQUIRY",
        )
        return ActivationRunbook(
            VERSION, WAITING, False, completed, ORDERED_STEPS,
            ORDERED_STEPS[0], ROLLBACK_ORDER,
            d1.row_count, 0, artifact.item_count, False,
            (
                "OFFICIAL_RESPONSE_REQUIRED_BEFORE_ACTIVATION",
                "EXPLICIT_PRODUCTION_APPROVAL_REQUIRED",
                "FREE_PLAN_ONLY",
            ),
        )
    except Exception:
        return ActivationRunbook(
            VERSION, FAIL_CLOSED, False, (), (), None, ROLLBACK_ORDER,
            None, None, None, False, ("ACTIVATION_RUNBOOK_INPUT_INVALID",),
        )


def current_runbook() -> ActivationRunbook:
    return build_runbook(
        revenue_mvp_official_followup_status.current_status(),
        revenue_mvp_publication_artifact_evidence.assess_evidence(),
        affiliate_d1_production_state.assess(
            affiliate_d1_production_state.current_evidence()
        ),
        affiliate_runtime_deployment_preflight.assess_preflight(
            affiliate_runtime_deployment_preflight.current_input()
        ),
    )


def main() -> int:
    result = current_runbook()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == WAITING else 2


if __name__ == "__main__":
    raise SystemExit(main())
