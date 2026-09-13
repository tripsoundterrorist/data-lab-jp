"""Read-only work lanes derived from the Revenue MVP release gate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from typing import Any

import revenue_mvp_lifecycle_condition_evidence
import revenue_mvp_official_followup_status
import revenue_mvp_publication_artifact_evidence
import revenue_mvp_release_gate
import revenue_mvp_sort_condition_evidence
import revenue_mvp_temporal_continuation_assessment
import revenue_mvp_temporal_active_runner_candidate_evidence
import revenue_mvp_temporal_series_candidate_evidence


VERSION = "0.8"
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
DERIVED_SAFE_ACTION = "PREPARE_TEMPORAL_SERIES_PIPELINE_CONNECTION_REVIEW"
DERIVED_ACTIVE_RUNNER_ACTION = "REVIEW_ACTIVE_RUNNER_CONNECTION_APPROVAL"
EXTERNAL_BOUNDARY_ORDER = (
    "WAIT_FOR_DMM_LIFECYCLE_SEMANTICS_RESPONSE",
    "WAIT_FOR_DMM_SORT_SEMANTICS_RESPONSE",
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
    publication_artifact_evidence_status: str
    temporal_continuation_status: str
    temporal_series_candidate_evidence_status: str
    temporal_active_runner_candidate_evidence_status: str
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
    release: Any,
    lifecycle_evidence: Any,
    sort_evidence: Any,
    temporal_continuation: Any | None = None,
    temporal_series_evidence: Any | None = None,
    temporal_active_runner_evidence: Any | None = None,
    followup_status: Any | None = None,
    artifact_evidence: Any | None = None,
) -> NextGatePlan:
    """Classify exact known actions without authorizing either lane."""

    try:
        if temporal_continuation is None:
            temporal_continuation = (
                revenue_mvp_temporal_continuation_assessment
                .assess_temporal_continuation(as_of=datetime.now(timezone.utc))
            )
        if temporal_series_evidence is None:
            temporal_series_evidence = (
                revenue_mvp_temporal_series_candidate_evidence
                .assess_temporal_series_candidate_evidence()
            )
        if temporal_active_runner_evidence is None:
            temporal_active_runner_evidence = (
                revenue_mvp_temporal_active_runner_candidate_evidence
                .assess_candidate_evidence()
            )
        if followup_status is None:
            followup_status = revenue_mvp_official_followup_status.current_status()
        if artifact_evidence is None:
            artifact_evidence = revenue_mvp_publication_artifact_evidence.assess_evidence()
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
            or temporal_continuation.version
            != revenue_mvp_temporal_continuation_assessment.VERSION
            or temporal_continuation.status not in {
                revenue_mvp_temporal_continuation_assessment.WINDOW_CANDIDATE,
                revenue_mvp_temporal_continuation_assessment.WAIT,
                revenue_mvp_temporal_continuation_assessment.LONG_GAP_BLOCKED,
            }
            or temporal_continuation.api_request_authorized is not False
            or temporal_continuation.state_write_authorized is not False
            or not isinstance(
                temporal_continuation.fresh_baseline_policy_required, bool
            )
            or not isinstance(temporal_continuation.populations_found, int)
            or temporal_series_evidence.version
            != revenue_mvp_temporal_series_candidate_evidence.VERSION
            or temporal_series_evidence.status not in {
                revenue_mvp_temporal_series_candidate_evidence.EVIDENCE_READY,
                revenue_mvp_temporal_series_candidate_evidence.BLOCKED,
            }
            or not isinstance(
                temporal_series_evidence.implementation_evidence_candidate,
                bool,
            )
            or temporal_series_evidence.isolated_integration_adapter_verified
            is not True
            or temporal_series_evidence.active_pipeline_connected is not False
            or temporal_series_evidence.api_request_authorized is not False
            or temporal_series_evidence.state_write_authorized is not False
            or temporal_series_evidence.baseline_activation_authorized is not False
            or not isinstance(temporal_series_evidence.checks_passed, int)
            or not isinstance(temporal_series_evidence.checks_required, int)
            or temporal_active_runner_evidence.version
            != revenue_mvp_temporal_active_runner_candidate_evidence.VERSION
            or temporal_active_runner_evidence.status not in {
                revenue_mvp_temporal_active_runner_candidate_evidence.EVIDENCE_READY,
                revenue_mvp_temporal_active_runner_candidate_evidence.BLOCKED,
            }
            or not isinstance(
                temporal_active_runner_evidence.implementation_evidence_candidate,
                bool,
            )
            or not isinstance(
                temporal_active_runner_evidence.test_filesystem_access_performed,
                bool,
            )
            or temporal_active_runner_evidence.active_pipeline_connected is not False
            or temporal_active_runner_evidence.api_request_authorized is not False
            or temporal_active_runner_evidence.production_write_authorized is not False
            or temporal_active_runner_evidence.scheduler_change_authorized is not False
            or temporal_active_runner_evidence.deploy_allowed is not False
            or not isinstance(temporal_active_runner_evidence.checks_passed, int)
            or not isinstance(temporal_active_runner_evidence.checks_required, int)
            or followup_status.version
            != revenue_mvp_official_followup_status.VERSION
            or followup_status.status
            != revenue_mvp_official_followup_status.SUBMITTED_AWAITING_RESPONSE
            or followup_status.covered_blockers
            != ("DMM_LIFECYCLE_AVAILABILITY", "DMM_SORT_SEMANTICS")
            or followup_status.response_received is not False
            or followup_status.official_semantics_resolved is not False
            or followup_status.gate_unlock_allowed is not False
            or artifact_evidence.version
            != revenue_mvp_publication_artifact_evidence.VERSION
            or artifact_evidence.status not in {
                revenue_mvp_publication_artifact_evidence.EVIDENCE_READY,
                revenue_mvp_publication_artifact_evidence.BLOCKED,
            }
            or not isinstance(artifact_evidence.source_db_matches, bool)
            or not isinstance(artifact_evidence.artifact_validation_passed, bool)
            or artifact_evidence.publication_allowed is not False
            or artifact_evidence.production_write_performed is not False
            or artifact_evidence.gate_unlock_allowed is not False
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
        artifact_evidence_ready = (
            artifact_evidence.status
            == revenue_mvp_publication_artifact_evidence.EVIDENCE_READY
            and artifact_evidence.source_db_matches is True
            and artifact_evidence.artifact_validation_passed is True
            and type(artifact_evidence.item_count) is int
            and artifact_evidence.item_count > 0
        )
        temporal_integration_candidate = (
            "CONTINUE_TEMPORAL_OBSERVATION" in actions
            and temporal_continuation.status
            == revenue_mvp_temporal_continuation_assessment.LONG_GAP_BLOCKED
            and temporal_continuation.fresh_baseline_policy_required is True
            and temporal_continuation.populations_found == 4
            and temporal_series_evidence.status
            == revenue_mvp_temporal_series_candidate_evidence.EVIDENCE_READY
            and temporal_series_evidence.implementation_evidence_candidate is True
            and temporal_series_evidence.checks_required == 8
            and temporal_series_evidence.checks_passed
            == temporal_series_evidence.checks_required
        )
        active_runner_candidate_ready = (
            temporal_integration_candidate
            and temporal_active_runner_evidence.status
            == revenue_mvp_temporal_active_runner_candidate_evidence.EVIDENCE_READY
            and temporal_active_runner_evidence.implementation_evidence_candidate is True
            and temporal_active_runner_evidence.test_filesystem_access_performed is True
            and temporal_active_runner_evidence.checks_required == 8
            and temporal_active_runner_evidence.checks_passed
            == temporal_active_runner_evidence.checks_required
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
                or temporal_integration_candidate
                and action == "CONTINUE_TEMPORAL_OBSERVATION"
                or artifact_evidence_ready
                and action == "PREPARE_PUBLICATION_ARTIFACT_VALIDATION"
            )
        )
        if temporal_integration_candidate:
            local = (
                DERIVED_ACTIVE_RUNNER_ACTION
                if active_runner_candidate_ready
                else DERIVED_SAFE_ACTION,
            ) + local
        external_actions = set(actions)
        if evidence_ready:
            external_actions.add("WAIT_FOR_DMM_LIFECYCLE_SEMANTICS_RESPONSE")
        if sort_evidence_ready:
            external_actions.add("WAIT_FOR_DMM_SORT_SEMANTICS_RESPONSE")
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
            artifact_evidence.status,
            temporal_continuation.status,
            temporal_series_evidence.status,
            temporal_active_runner_evidence.status,
            local,
            external,
            local[0] if local else None,
            ("SEPARATE_APPROVAL_REQUIRED", "WORK_LANES_CLASSIFIED"),
        )
    except Exception:
        return NextGatePlan(
            VERSION, FAIL_CLOSED, False, "UNKNOWN", "UNKNOWN", "UNKNOWN",
            "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN",
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
            revenue_mvp_temporal_continuation_assessment
            .assess_temporal_continuation(as_of=datetime.now(timezone.utc)),
            revenue_mvp_temporal_series_candidate_evidence
            .assess_temporal_series_candidate_evidence(),
            revenue_mvp_temporal_active_runner_candidate_evidence
            .assess_candidate_evidence(),
            revenue_mvp_official_followup_status.current_status(),
            revenue_mvp_publication_artifact_evidence.assess_evidence(),
        )
    except Exception:
        return NextGatePlan(
            VERSION, FAIL_CLOSED, False, "UNKNOWN", "UNKNOWN", "UNKNOWN",
            "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN",
            (), (), None,
            ("NEXT_GATE_PLAN_INTERNAL_ERROR",),
        )


def main() -> int:
    result = run_plan()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == BLOCKED else 2


if __name__ == "__main__":
    raise SystemExit(main())
