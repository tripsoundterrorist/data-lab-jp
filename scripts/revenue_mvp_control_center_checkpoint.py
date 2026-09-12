"""One sanitized, fail-closed checkpoint for the Revenue MVP control center."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

import affiliate_d1_production_state
import revenue_mvp_activation_runbook
import revenue_mvp_launch_rehearsal
import revenue_mvp_official_followup_status
import revenue_mvp_official_response_rehearsal
import revenue_mvp_publication_artifact_evidence


VERSION = "0.1"
READY_WAITING = "READY_WAITING_FOR_OFFICIAL_RESPONSE"
FAIL_CLOSED = "FAIL_CLOSED"
NEXT_ACTION = "WAIT_FOR_AND_INTAKE_OFFICIAL_RESPONSE"


@dataclass(frozen=True)
class ControlCenterCheckpoint:
    version: str
    status: str
    revenue_mvp_priority: str
    official_response_pending: bool
    public_artifact_item_count: int | None
    d1_row_count: int | None
    d1_enabled_row_count: int | None
    offline_launch_rehearsal_passed: bool
    official_response_rehearsal_passed: bool
    publication_allowed: bool
    production_activation_allowed: bool
    paid_plan_change_allowed: bool
    next_action: str
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(value["reason_codes"])
        return value


def build_checkpoint(
    followup: Any,
    artifact: Any,
    d1: Any,
    runbook: Any,
    launch_rehearsal: Any,
    response_rehearsal: Any,
) -> ControlCenterCheckpoint:
    """Combine bounded evidence without mutating a Gate or production state."""
    try:
        valid = (
            followup.version == revenue_mvp_official_followup_status.VERSION
            and followup.status
            == revenue_mvp_official_followup_status.SUBMITTED_AWAITING_RESPONSE
            and followup.response_received is False
            and followup.gate_unlock_allowed is False
            and artifact.version == revenue_mvp_publication_artifact_evidence.VERSION
            and artifact.status
            == revenue_mvp_publication_artifact_evidence.EVIDENCE_READY
            and artifact.source_db_matches is True
            and artifact.artifact_validation_passed is True
            and artifact.publication_allowed is False
            and artifact.production_write_performed is False
            and artifact.gate_unlock_allowed is False
            and d1.version == affiliate_d1_production_state.VERSION
            and d1.status == affiliate_d1_production_state.READY
            and d1.lookup_ready is True
            and d1.all_rows_disabled is True
            and d1.all_rows_pending is True
            and d1.runtime_eligibility_empty is True
            and d1.cloudflare_write_allowed is False
            and d1.deployment_allowed is False
            and d1.paid_plan_change_allowed is False
            and runbook.version == revenue_mvp_activation_runbook.VERSION
            and runbook.status == revenue_mvp_activation_runbook.WAITING
            and runbook.production_activation_allowed is False
            and runbook.paid_plan_change_allowed is False
            and runbook.next_step == "INTAKE_AND_CLASSIFY_DMM_RESPONSE"
            and launch_rehearsal.version == revenue_mvp_launch_rehearsal.VERSION
            and launch_rehearsal.status == revenue_mvp_launch_rehearsal.PASS
            and launch_rehearsal.production_write_performed is False
            and launch_rehearsal.network_request_performed is False
            and launch_rehearsal.deploy_allowed is False
            and launch_rehearsal.paid_plan_change_allowed is False
            and response_rehearsal.version
            == revenue_mvp_official_response_rehearsal.VERSION
            and response_rehearsal.status
            == revenue_mvp_official_response_rehearsal.PASS
            and response_rehearsal.gate_unlock_allowed is False
            and response_rehearsal.production_activation_allowed is False
            and artifact.item_count == d1.row_count
            and artifact.item_count == runbook.public_artifact_item_count
            and d1.row_count == runbook.d1_row_count
            and runbook.d1_runtime_eligible_count == 0
        )
        if not valid:
            raise ValueError("checkpoint evidence mismatch")
        return ControlCenterCheckpoint(
            VERSION, READY_WAITING, "P0", True, artifact.item_count,
            d1.row_count, 0, True, True, False, False, False, NEXT_ACTION,
            (
                "CURRENT_EVIDENCE_CONSISTENT",
                "OFFICIAL_RESPONSE_IS_ONLY_CURRENT_EXTERNAL_BLOCKER",
                "ALL_PUBLICATION_AND_BILLING_MUTATIONS_REMAIN_CLOSED",
            ),
        )
    except Exception:
        return ControlCenterCheckpoint(
            VERSION, FAIL_CLOSED, "P0", True, None, None, None,
            False, False, False, False, False,
            "RECONCILE_CONTROL_CENTER_EVIDENCE",
            ("CONTROL_CENTER_EVIDENCE_INVALID_OR_STALE",),
        )


def current_checkpoint() -> ControlCenterCheckpoint:
    followup = revenue_mvp_official_followup_status.current_status()
    artifact = revenue_mvp_publication_artifact_evidence.assess_evidence()
    d1 = affiliate_d1_production_state.assess(
        affiliate_d1_production_state.current_evidence()
    )
    return build_checkpoint(
        followup,
        artifact,
        d1,
        revenue_mvp_activation_runbook.build_runbook(
            followup,
            artifact,
            d1,
            revenue_mvp_activation_runbook.affiliate_runtime_deployment_preflight.assess_preflight(
                revenue_mvp_activation_runbook.affiliate_runtime_deployment_preflight.current_input()
            ),
        ),
        revenue_mvp_launch_rehearsal.run_rehearsal(),
        revenue_mvp_official_response_rehearsal.run_rehearsal(),
    )


def main() -> int:
    result = current_checkpoint()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY_WAITING else 2


if __name__ == "__main__":
    raise SystemExit(main())
