"""Read-only work lanes derived from the Revenue MVP release gate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

import revenue_mvp_lifecycle_condition_evidence
import revenue_mvp_release_gate
import revenue_mvp_sort_condition_evidence


VERSION = "0.3"
BLOCKED = "BLOCKED"
FAIL_CLOSED = "FAIL_CLOSED"

SAFE_LOCAL_ORDER = (
    "IMPLEMENT_DMM_LIFECYCLE_CONDITIONS",
    "IMPLEMENT_DMM_SORT_SEMANTICS_CONDITIONS",
    "CONTINUE_TEMPORAL_OBSERVATION",
    "PREPARE_PUBLICATION_ARTIFACT_VALIDATION",
    "MONITOR_INDEX_COVERAGE",
    "DO_NOT_REQUEST_ITEM_INDEXING",
    "RUN_PRIVATE_LOOKUP_D1_IMPORT_PREFLIGHT",
    "ENABLE_IDENTIFIER_AND_URL_LOG_REDACTION",
    "DISABLE_AFFILIATE_REDIRECT_CACHE",
    "CONNECT_AFFILIATE_RUNTIME_CHAIN",
    "ADD_PROXIMATE_PR_DISCLOSURE",
)
EXTERNAL_BOUNDARY_ORDER = (
    "OBTAIN_SEPARATE_DMM_LIFECYCLE_SEMANTICS_CONFIRMATION",
    "OBTAIN_SEPARATE_DMM_SORT_SEMANTICS_CONFIRMATION",
    "VERIFY_PRODUCTION_DOMAIN_APPROVAL",
    "WAIT_FOR_SNS_SITE_APPROVAL_AND_IMPLEMENT_CONDITIONS",
    "CONFIGURE_REQUIRED_SECRET_BINDINGS",
    "CONFIGURE_PRIVATE_ITEM_LOOKUP",
    "CONFIGURE_DEDICATED_GET_HEAD_ROUTE",
    "CONFIGURE_BOUNDED_PER_CLIENT_RATE_LIMIT",
)
DERIVED_EXTERNAL_ACTIONS = frozenset(
    (
        "OBTAIN_SEPARATE_DMM_LIFECYCLE_SEMANTICS_CONFIRMATION",
        "OBTAIN_SEPARATE_DMM_SORT_SEMANTICS_CONFIRMATION",
    )
)
KNOWN_RELEASE_ACTIONS = frozenset(
    SAFE_LOCAL_ORDER
    + tuple(
        action
        for action in EXTERNAL_BOUNDARY_ORDER
        if action not in DERIVED_EXTERNAL_ACTIONS
    )
)


@dataclass(frozen=True)
class NextGatePlan:
    version: str
    status: str
    production_release_allowed: bool
    release_gate_status: str
    lifecycle_condition_evidence_status: str
    sort_condition_evidence_status: str
    safe_local_actions: tuple[str, ...]
    external_boundary_actions: tuple[str, ...]
    next_safe_local_action: str | None
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["safe_local_actions"] = list(self.safe_local_actions)
        value["external_boundary_actions"] = list(self.external_boundary_actions)
        value["reason_codes"] = list(self.reason_codes)
        return value


def build_plan(
    release: Any, lifecycle_evidence: Any, sort_evidence: Any
) -> NextGatePlan:
    """Classify exact known actions without authorizing either lane."""

    try:
        actions = release.next_actions
        if (
            not isinstance(actions, tuple)
            or any(not isinstance(action, str) for action in actions)
            or len(actions) != len(set(actions))
            or not set(actions).issubset(KNOWN_RELEASE_ACTIONS)
            or not isinstance(release.status, str)
            or lifecycle_evidence.version
            != revenue_mvp_lifecycle_condition_evidence.VERSION
            or lifecycle_evidence.status not in {
                revenue_mvp_lifecycle_condition_evidence.EVIDENCE_READY,
                revenue_mvp_lifecycle_condition_evidence.BLOCKED,
            }
            or not isinstance(
                lifecycle_evidence.implementation_evidence_candidate, bool
            )
            or lifecycle_evidence.official_semantics_resolved is not False
            or lifecycle_evidence.publication_gate_unlock_allowed is not False
            or not isinstance(lifecycle_evidence.checks_passed, int)
            or not isinstance(lifecycle_evidence.checks_required, int)
            or sort_evidence.version
            != revenue_mvp_sort_condition_evidence.VERSION
            or sort_evidence.status not in {
                revenue_mvp_sort_condition_evidence.EVIDENCE_READY,
                revenue_mvp_sort_condition_evidence.BLOCKED,
            }
            or not isinstance(
                sort_evidence.implementation_evidence_candidate, bool
            )
            or sort_evidence.official_semantics_resolved is not False
            or sort_evidence.publication_gate_unlock_allowed is not False
            or not isinstance(sort_evidence.checks_passed, int)
            or not isinstance(sort_evidence.checks_required, int)
        ):
            raise ValueError("invalid release summary")
        evidence_ready = (
            lifecycle_evidence.status
            == revenue_mvp_lifecycle_condition_evidence.EVIDENCE_READY
            and lifecycle_evidence.implementation_evidence_candidate is True
            and lifecycle_evidence.checks_required == 5
            and lifecycle_evidence.checks_passed
            == lifecycle_evidence.checks_required
        )
        sort_evidence_ready = (
            sort_evidence.status
            == revenue_mvp_sort_condition_evidence.EVIDENCE_READY
            and sort_evidence.implementation_evidence_candidate is True
            and sort_evidence.checks_required == 6
            and sort_evidence.checks_passed == sort_evidence.checks_required
        )
        local = tuple(
            action
            for action in SAFE_LOCAL_ORDER
            if action in actions
            and not (
                evidence_ready
                and action == "IMPLEMENT_DMM_LIFECYCLE_CONDITIONS"
                or sort_evidence_ready
                and action == "IMPLEMENT_DMM_SORT_SEMANTICS_CONDITIONS"
            )
        )
        external_actions = set(actions)
        if evidence_ready:
            external_actions.add(
                "OBTAIN_SEPARATE_DMM_LIFECYCLE_SEMANTICS_CONFIRMATION"
            )
        if sort_evidence_ready:
            external_actions.add(
                "OBTAIN_SEPARATE_DMM_SORT_SEMANTICS_CONFIRMATION"
            )
        external = tuple(
            action
            for action in EXTERNAL_BOUNDARY_ORDER
            if action in external_actions
        )
        return NextGatePlan(
            VERSION,
            BLOCKED,
            False,
            release.status,
            lifecycle_evidence.status,
            sort_evidence.status,
            local,
            external,
            local[0] if local else None,
            ("SEPARATE_APPROVAL_REQUIRED", "WORK_LANES_CLASSIFIED"),
        )
    except Exception:
        return NextGatePlan(
            VERSION, FAIL_CLOSED, False, "UNKNOWN", "UNKNOWN", "UNKNOWN",
            (), (), None,
            ("NEXT_GATE_PLAN_INPUT_INVALID",),
        )


def run_plan() -> NextGatePlan:
    try:
        return build_plan(
            revenue_mvp_release_gate.run_gate(),
            revenue_mvp_lifecycle_condition_evidence
            .assess_lifecycle_condition_evidence(),
            revenue_mvp_sort_condition_evidence
            .assess_sort_condition_evidence(),
        )
    except Exception:
        return NextGatePlan(
            VERSION, FAIL_CLOSED, False, "UNKNOWN", "UNKNOWN", "UNKNOWN",
            (), (), None,
            ("NEXT_GATE_PLAN_INTERNAL_ERROR",),
        )


def main() -> int:
    result = run_plan()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == BLOCKED else 2


if __name__ == "__main__":
    raise SystemExit(main())
