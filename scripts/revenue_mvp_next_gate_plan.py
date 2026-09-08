"""Read-only work lanes derived from the Revenue MVP release gate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

import revenue_mvp_release_gate


VERSION = "0.1"
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
    "VERIFY_PRODUCTION_DOMAIN_APPROVAL",
    "WAIT_FOR_SNS_SITE_APPROVAL_AND_IMPLEMENT_CONDITIONS",
    "CONFIGURE_REQUIRED_SECRET_BINDINGS",
    "CONFIGURE_PRIVATE_ITEM_LOOKUP",
    "CONFIGURE_DEDICATED_GET_HEAD_ROUTE",
    "CONFIGURE_BOUNDED_PER_CLIENT_RATE_LIMIT",
)
KNOWN_ACTIONS = frozenset(SAFE_LOCAL_ORDER + EXTERNAL_BOUNDARY_ORDER)


@dataclass(frozen=True)
class NextGatePlan:
    version: str
    status: str
    production_release_allowed: bool
    release_gate_status: str
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


def build_plan(release: Any) -> NextGatePlan:
    """Classify exact known actions without authorizing either lane."""

    try:
        actions = release.next_actions
        if (
            not isinstance(actions, tuple)
            or any(not isinstance(action, str) for action in actions)
            or len(actions) != len(set(actions))
            or not set(actions).issubset(KNOWN_ACTIONS)
            or not isinstance(release.status, str)
        ):
            raise ValueError("invalid release summary")
        local = tuple(action for action in SAFE_LOCAL_ORDER if action in actions)
        external = tuple(
            action for action in EXTERNAL_BOUNDARY_ORDER if action in actions
        )
        return NextGatePlan(
            VERSION,
            BLOCKED,
            False,
            release.status,
            local,
            external,
            local[0] if local else None,
            ("SEPARATE_APPROVAL_REQUIRED", "WORK_LANES_CLASSIFIED"),
        )
    except Exception:
        return NextGatePlan(
            VERSION, FAIL_CLOSED, False, "UNKNOWN", (), (), None,
            ("NEXT_GATE_PLAN_INPUT_INVALID",),
        )


def run_plan() -> NextGatePlan:
    try:
        return build_plan(revenue_mvp_release_gate.run_gate())
    except Exception:
        return NextGatePlan(
            VERSION, FAIL_CLOSED, False, "UNKNOWN", (), (), None,
            ("NEXT_GATE_PLAN_INTERNAL_ERROR",),
        )


def main() -> int:
    result = run_plan()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == BLOCKED else 2


if __name__ == "__main__":
    raise SystemExit(main())
