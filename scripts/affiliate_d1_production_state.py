"""Sanitized, non-deploying evidence for the production D1 lookup state."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any


VERSION = "0.1"
READY = "READY_FOR_INERT_RUNTIME_REVIEW"
BLOCKED = "BLOCKED"
FAIL_CLOSED = "FAIL_CLOSED"
EXPECTED_ROW_COUNT = 861
EXPECTED_BINDING_NAME = "AFFILIATE_ITEM_LOOKUP"


@dataclass(frozen=True)
class D1ProductionEvidence:
    free_plan_confirmed: bool
    data_binding_name: str
    table_present: bool
    eligible_view_present: bool
    row_count: int
    pending_row_count: int
    enabled_row_count: int
    eligible_row_count: int
    exact_candidate_mapping_verified: bool


@dataclass(frozen=True)
class D1ProductionStateResult:
    version: str
    status: str
    lookup_ready: bool
    free_plan_compatible: bool
    row_count: int
    all_rows_disabled: bool
    all_rows_pending: bool
    runtime_eligibility_empty: bool
    exact_candidate_mapping_verified: bool
    cloudflare_write_allowed: bool
    deployment_allowed: bool
    paid_plan_change_allowed: bool
    reason_codes: tuple[str, ...]
    next_actions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        value["next_actions"] = list(self.next_actions)
        return value


def current_evidence() -> D1ProductionEvidence:
    """Return sanitized operator- and read-only-query-confirmed facts."""

    return D1ProductionEvidence(
        free_plan_confirmed=True,
        data_binding_name=EXPECTED_BINDING_NAME,
        table_present=True,
        eligible_view_present=True,
        row_count=EXPECTED_ROW_COUNT,
        pending_row_count=EXPECTED_ROW_COUNT,
        enabled_row_count=0,
        eligible_row_count=0,
        exact_candidate_mapping_verified=True,
    )


def assess(evidence: Any) -> D1ProductionStateResult:
    """Assess safe counts and booleans without accepting IDs, URLs, or secrets."""

    try:
        if not isinstance(evidence, D1ProductionEvidence):
            raise ValueError("invalid evidence")
        boolean_fields = (
            evidence.free_plan_confirmed,
            evidence.table_present,
            evidence.eligible_view_present,
            evidence.exact_candidate_mapping_verified,
        )
        count_fields = (
            evidence.row_count,
            evidence.pending_row_count,
            evidence.enabled_row_count,
            evidence.eligible_row_count,
        )
        if not all(isinstance(value, bool) for value in boolean_fields):
            raise ValueError("invalid boolean")
        if not all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in count_fields
        ):
            raise ValueError("invalid count")
        if evidence.data_binding_name != EXPECTED_BINDING_NAME:
            raise ValueError("invalid binding")

        reasons: list[str] = []
        actions: list[str] = []
        if not evidence.free_plan_confirmed:
            reasons.append("FREE_PLAN_NOT_CONFIRMED")
            actions.append("STOP_AND_NOTIFY_BEFORE_BILLING_CHANGE")
        if not evidence.table_present or not evidence.eligible_view_present:
            reasons.append("D1_SCHEMA_NOT_READY")
            actions.append("VERIFY_D1_SCHEMA_READ_ONLY")
        if evidence.row_count != EXPECTED_ROW_COUNT:
            reasons.append("D1_ROW_COUNT_MISMATCH")
            actions.append("RECONCILE_D1_LOOKUP_FAIL_CLOSED")
        if evidence.pending_row_count != evidence.row_count:
            reasons.append("D1_PENDING_STATE_MISMATCH")
            actions.append("STOP_AND_REVIEW_D1_STATE")
        if evidence.enabled_row_count != 0:
            reasons.append("D1_AFFILIATE_ROW_ENABLED")
            actions.append("STOP_AND_DISABLE_AFFILIATE_ROWS")
        if evidence.eligible_row_count != 0:
            reasons.append("D1_RUNTIME_ELIGIBILITY_NOT_EMPTY")
            actions.append("STOP_AND_CLOSE_RUNTIME_ELIGIBILITY")
        if not evidence.exact_candidate_mapping_verified:
            reasons.append("D1_EXACT_MAPPING_NOT_VERIFIED")
            actions.append("VERIFY_REMOTE_CANDIDATE_MAPPING")

        ready = not reasons
        return D1ProductionStateResult(
            VERSION,
            READY if ready else BLOCKED,
            ready,
            evidence.free_plan_confirmed,
            evidence.row_count,
            evidence.enabled_row_count == 0,
            evidence.pending_row_count == evidence.row_count,
            evidence.eligible_row_count == 0,
            evidence.exact_candidate_mapping_verified,
            False,
            False,
            False,
            tuple(reasons) or ("INERT_D1_PRODUCTION_STATE_VERIFIED",),
            tuple(actions),
        )
    except Exception:
        return D1ProductionStateResult(
            VERSION,
            FAIL_CLOSED,
            False,
            False,
            0,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            ("D1_PRODUCTION_STATE_INTERNAL_ERROR",),
            (),
        )


def main() -> int:
    result = assess(current_evidence())
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {READY, BLOCKED} else 2


if __name__ == "__main__":
    raise SystemExit(main())
