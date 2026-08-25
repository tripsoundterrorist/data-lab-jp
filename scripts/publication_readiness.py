"""Pure, read-only aggregation of DATA LAB publication readiness."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Mapping

import collection_policy
import lifecycle_decision  # Imported dependency boundary; no lifecycle inference.
import product_lifecycle  # Imported dependency boundary; no state mutation.
import product_verification  # Imported dependency boundary; no API access.
from official_blocker_policy import (
    BLOCKER_IDS, BLOCKERS, INTERNAL_APPROVAL_REQUIRED,
    PENDING_OFFICIAL_CONFIRMATION, POLICY_VERSION as BLOCKER_POLICY_VERSION,
    PUBLICATION_BLOCKER, RESOLVED,
)
from publication_gate import (
    CLOSED, GATE_VERSION, PASS, PUBLIC_POLICY_VERSION, PUBLIC_SCHEMA_VERSION,
)
from rights_decision_policy import (
    APPROVED, CONDITIONALLY_APPROVED, PENDING_SEPARATE_POLICY, PROHIBITED,
    POLICY_VERSION as RIGHTS_POLICY_VERSION, RIGHTS_DECISIONS,
    SECRET_BEARING_FIELDS,
)


REPORT_VERSION = "0.1"
READY = "READY"
PASS_CATEGORY = "PASS"
BLOCKED = "BLOCKED"
NOT_EVALUATED = "NOT_EVALUATED"
FAIL_CLOSED = "FAIL_CLOSED"
READINESS_CATEGORIES = frozenset({
    READY, PASS_CATEGORY, BLOCKED, PENDING_OFFICIAL_CONFIRMATION,
    INTERNAL_APPROVAL_REQUIRED, NOT_EVALUATED, FAIL_CLOSED,
})

REQUIRED_GATES = (
    "RIGHTS_GATE", "DATA_POLICY_GATE", "LIFECYCLE_GATE",
    "SEMANTICS_GATE", "PUBLICATION_STATUS_GATE",
)
KNOWN_GATE_STATUSES = frozenset({PASS, CLOSED, PENDING_OFFICIAL_CONFIRMATION})
NEXT_ACTION_ORDER = (
    "WAIT_FOR_DMM_LIFECYCLE_RESPONSE",
    "WAIT_FOR_DMM_SORT_SEMANTICS_RESPONSE",
    "CONTINUE_TEMPORAL_OBSERVATION",
    "PREPARE_PUBLICATION_ARTIFACT_VALIDATION",
)
REASON_ORDER = (
    "DEPENDENCY_VERSION_MISMATCH", "MALFORMED_INPUT", "UNSAFE_INPUT",
    "UNKNOWN_GATE", "UNKNOWN_GATE_STATUS", "UNKNOWN_BLOCKER",
    "UNKNOWN_BLOCKER_STATUS", "CONTRADICTORY_STATUS",
    "LIFECYCLE_OFFICIAL_CONFIRMATION_PENDING",
    "SORT_SEMANTICS_OFFICIAL_CONFIRMATION_PENDING",
    "PUBLICATION_ACTIVATION_REQUIRED", "PUBLICATION_STATUS_NOT_PUBLIC",
)

_UNSAFE_KEY = re.compile(
    r"(?i)^(?:api_id|affiliate_id|raw_support_email|raw_email|raw_api_response|"
    r"content_id|content_ids|anonymous_id|anonymous_ids|anonymous_item_ids|"
    r"credential|credentials|traceback|exception|absolute_path|file_path)$"
)
_UNSAFE_VALUE = re.compile(
    r"(?i)(?:api|affiliate)[_-]?id\s*[:=]|bearer\s+[a-z0-9._~-]{6,}|"
    r"(?:[a-z]:[\\/]|/home/|/users/)|traceback \(most recent call last\)"
)


@dataclass(frozen=True)
class ReadinessInput:
    report_version: str
    gate_version: str
    rights_policy_version: str
    blocker_policy_version: str
    public_schema_version: str
    public_policy_version: str
    collection_policy_version: str
    lifecycle_policy_version: str
    gates: Mapping[str, str]
    publication_status: str
    overall_eligible: bool
    blockers: Mapping[str, str]
    temporal_observation: Mapping[str, Any]


@dataclass(frozen=True)
class PublicationReadinessReport:
    report_version: str
    generated_at: str
    overall_readiness: str
    overall_eligible: bool
    gate_summaries: tuple[dict[str, str], ...]
    blocker_summaries: tuple[dict[str, Any], ...]
    rights_summary: dict[str, Any]
    lifecycle_summary: tuple[str, ...]
    semantics_summary: tuple[str, ...]
    temporal_observational_summary: dict[str, Any]
    publication_activation_requirements: tuple[str, ...]
    next_actions: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_version": self.report_version,
            "generated_at": self.generated_at,
            "overall_readiness": self.overall_readiness,
            "overall_eligible": self.overall_eligible,
            "gate_summaries": list(self.gate_summaries),
            "blocker_summaries": list(self.blocker_summaries),
            "rights_summary": self.rights_summary,
            "lifecycle_summary": list(self.lifecycle_summary),
            "semantics_summary": list(self.semantics_summary),
            "temporal_observational_summary": self.temporal_observational_summary,
            "publication_activation_requirements": list(self.publication_activation_requirements),
            "next_actions": list(self.next_actions),
            "reason_codes": list(self.reason_codes),
        }


def current_input(*, temporal_observation: Mapping[str, Any] | None = None) -> ReadinessInput:
    return ReadinessInput(
        REPORT_VERSION, GATE_VERSION, RIGHTS_POLICY_VERSION, BLOCKER_POLICY_VERSION,
        PUBLIC_SCHEMA_VERSION, PUBLIC_POLICY_VERSION, collection_policy.POLICY_VERSION,
        lifecycle_decision.POLICY_VERSION,
        {
            "RIGHTS_GATE": PASS, "DATA_POLICY_GATE": PASS,
            "LIFECYCLE_GATE": PENDING_OFFICIAL_CONFIRMATION,
            "SEMANTICS_GATE": PENDING_OFFICIAL_CONFIRMATION,
            "PUBLICATION_STATUS_GATE": CLOSED,
        },
        "local_validation_only", False,
        {blocker_id: BLOCKERS[blocker_id].status for blocker_id in BLOCKER_IDS},
        temporal_observation or {
            "day1_baseline_exists": True, "day2_comparison_exists": True,
            "history_count": 1, "production_readiness": NOT_EVALUATED,
        },
    )


def _unsafe(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            not isinstance(key, str) or _UNSAFE_KEY.fullmatch(key) is not None
            or _unsafe(child) for key, child in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_unsafe(child) for child in value)
    return isinstance(value, str) and _UNSAFE_VALUE.search(value) is not None


def _rights_summary() -> dict[str, Any]:
    groups: dict[str, list[str]] = {
        APPROVED: [], PROHIBITED: [], CONDITIONALLY_APPROVED: [],
        PENDING_SEPARATE_POLICY: [],
    }
    hidden_secret_fields = 0
    for field, decision in RIGHTS_DECISIONS.items():
        if decision.public_display not in groups:
            continue
        if field in SECRET_BEARING_FIELDS:
            hidden_secret_fields += 1
            continue
        groups[decision.public_display].append(field)
    return {
        "counts": {
            state: sum(row.public_display == state for row in RIGHTS_DECISIONS.values())
            for state in groups
        },
        "fields": {state: sorted(fields) for state, fields in groups.items()},
        "secret_field_names_redacted": hidden_secret_fields,
        "rights_do_not_override_other_gates": True,
    }


def _safe_temporal(value: Mapping[str, Any]) -> dict[str, Any] | None:
    allowed = {
        "day1_baseline_exists", "day2_comparison_exists", "history_count",
        "production_readiness",
    }
    if set(value) - allowed or _unsafe(value):
        return None
    baseline = value.get("day1_baseline_exists")
    comparison = value.get("day2_comparison_exists")
    history = value.get("history_count")
    readiness = value.get("production_readiness", NOT_EVALUATED)
    if not isinstance(baseline, bool) or not isinstance(comparison, bool):
        return None
    if not isinstance(history, int) or isinstance(history, bool) or history < 0:
        return None
    if readiness != NOT_EVALUATED:
        return None
    return {
        "day1_baseline_exists": baseline, "day2_comparison_exists": comparison,
        "history_count": history, "production_readiness": NOT_EVALUATED,
        "interpretation": "OBSERVATIONAL_ONLY",
    }


def _fail_closed(generated_at: datetime, reasons: set[str]) -> PublicationReadinessReport:
    reasons.add("MALFORMED_INPUT") if not reasons else None
    return PublicationReadinessReport(
        REPORT_VERSION, generated_at.isoformat(), FAIL_CLOSED, False, (), (),
        {}, (), (), {}, (), (),
        tuple(code for code in REASON_ORDER if code in reasons),
    )


def build_report(value: Any, *, generated_at: datetime) -> PublicationReadinessReport:
    try:
        reasons: set[str] = set()
        if not isinstance(generated_at, datetime) or generated_at.tzinfo is None:
            return _fail_closed(datetime.now(timezone.utc), {"MALFORMED_INPUT"})
        if not isinstance(value, ReadinessInput):
            return _fail_closed(generated_at, {"MALFORMED_INPUT"})
        expected_versions = (
            REPORT_VERSION, GATE_VERSION, RIGHTS_POLICY_VERSION, BLOCKER_POLICY_VERSION,
            PUBLIC_SCHEMA_VERSION, PUBLIC_POLICY_VERSION, collection_policy.POLICY_VERSION,
            lifecycle_decision.POLICY_VERSION,
        )
        actual_versions = (
            value.report_version, value.gate_version, value.rights_policy_version,
            value.blocker_policy_version, value.public_schema_version,
            value.public_policy_version, value.collection_policy_version,
            value.lifecycle_policy_version,
        )
        if actual_versions != expected_versions:
            reasons.add("DEPENDENCY_VERSION_MISMATCH")
        if _unsafe(value.temporal_observation):
            reasons.add("UNSAFE_INPUT")
        if not isinstance(value.gates, Mapping) or set(value.gates) != set(REQUIRED_GATES):
            reasons.add("UNKNOWN_GATE")
        elif any(status not in KNOWN_GATE_STATUSES for status in value.gates.values()):
            reasons.add("UNKNOWN_GATE_STATUS")
        if not isinstance(value.blockers, Mapping) or set(value.blockers) != set(BLOCKER_IDS):
            reasons.add("UNKNOWN_BLOCKER")
        elif any(status not in {PENDING_OFFICIAL_CONFIRMATION, INTERNAL_APPROVAL_REQUIRED, RESOLVED} for status in value.blockers.values()):
            reasons.add("UNKNOWN_BLOCKER_STATUS")
        temporal = _safe_temporal(value.temporal_observation) if isinstance(value.temporal_observation, Mapping) else None
        if temporal is None:
            reasons.add("MALFORMED_INPUT")
        if reasons:
            return _fail_closed(generated_at, reasons)

        gates = dict(value.gates)
        all_gate_pass = all(gates[name] == PASS for name in REQUIRED_GATES)
        official_resolved = all(
            value.blockers[name] == RESOLVED
            for name in ("DMM_LIFECYCLE_AVAILABILITY", "DMM_SORT_SEMANTICS")
        )
        activation_resolved = value.blockers[PUBLICATION_BLOCKER] == RESOLVED
        consistent_ready = all_gate_pass and official_resolved and activation_resolved and value.publication_status == "public"
        if value.overall_eligible != consistent_ready:
            return _fail_closed(generated_at, {"CONTRADICTORY_STATUS"})
        if value.publication_status == "public" and not activation_resolved:
            return _fail_closed(generated_at, {"CONTRADICTORY_STATUS"})

        if gates["LIFECYCLE_GATE"] != PASS:
            reasons.add("LIFECYCLE_OFFICIAL_CONFIRMATION_PENDING")
        if gates["SEMANTICS_GATE"] != PASS:
            reasons.add("SORT_SEMANTICS_OFFICIAL_CONFIRMATION_PENDING")
        if not activation_resolved:
            reasons.add("PUBLICATION_ACTIVATION_REQUIRED")
        if value.publication_status != "public":
            reasons.add("PUBLICATION_STATUS_NOT_PUBLIC")
        blocker_actions = {
            "DMM_LIFECYCLE_AVAILABILITY": "WAIT_FOR_DMM_LIFECYCLE_RESPONSE",
            "DMM_SORT_SEMANTICS": "WAIT_FOR_DMM_SORT_SEMANTICS_RESPONSE",
            "PUBLICATION_ACTIVATION": "PREPARE_PUBLICATION_ARTIFACT_VALIDATION",
        }
        blocker_summaries = tuple({
            "blocker_id": blocker_id,
            "status": value.blockers[blocker_id],
            "affected_gate": BLOCKERS[blocker_id].affected_gate,
            "gate_unlock_allowed": BLOCKERS[blocker_id].gate_unlock_allowed,
            "safe_next_action": blocker_actions[blocker_id],
        } for blocker_id in BLOCKER_IDS)
        next_actions = tuple(action for action in NEXT_ACTION_ORDER if (
            action == "CONTINUE_TEMPORAL_OBSERVATION"
            or action in {row["safe_next_action"] for row in blocker_summaries if row["status"] != RESOLVED}
        ))
        return PublicationReadinessReport(
            REPORT_VERSION, generated_at.isoformat(), READY if value.overall_eligible else BLOCKED,
            value.overall_eligible,
            tuple({"gate": gate, "status": gates[gate]} for gate in REQUIRED_GATES),
            blocker_summaries, _rights_summary(),
            (
                "API_ZERO_RESULT_SEMANTICS_UNRESOLVED",
                "AVAILABILITY_SIGNAL_UNRESOLVED",
                "AFFILIATE_URL_SEMANTICS_UNRESOLVED",
                "API_INVISIBLE_PAGE_LINK_HANDLING_UNRESOLVED",
            ),
            (
                "RANK_SORT_OFFICIAL_DEFINITION_UNRESOLVED",
                "REVIEW_SORT_OFFICIAL_DEFINITION_UNRESOLVED",
                "POSITION_OFFSET_PUBLIC_INTERPRETATION_UNRESOLVED",
            ),
            temporal or {},
            (
                "REQUIRED_GATES_PASS", "ARTIFACT_VALIDATION_PASS",
                "PRODUCTION_BUILD_PASS", "DEPLOYMENT_PREFLIGHT_PASS",
                "PUBLICATION_STATUS_CHANGE_BY_SEPARATE_COMMIT",
                "EXPLICIT_INTERNAL_APPROVAL",
            ),
            next_actions, tuple(code for code in REASON_ORDER if code in reasons),
        )
    except Exception:
        safe_time = generated_at if isinstance(generated_at, datetime) and generated_at.tzinfo else datetime.now(timezone.utc)
        return _fail_closed(safe_time, {"MALFORMED_INPUT"})


__all__ = [
    "BLOCKED", "FAIL_CLOSED", "NOT_EVALUATED", "PASS_CATEGORY", "READY",
    "READINESS_CATEGORIES", "REPORT_VERSION", "PublicationReadinessReport",
    "ReadinessInput", "build_report", "current_input",
]
