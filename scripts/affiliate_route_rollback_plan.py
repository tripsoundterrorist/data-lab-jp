"""Pure, non-executing rollback plan for the future affiliate Worker route."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any


PLAN_VERSION = "0.1"
READY = "ROLLBACK_PLAN_READY"
FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class RollbackPlan:
    plan_version: str
    status: str
    executable: bool
    production_write_allowed: bool
    billing_change_allowed: bool
    ordered_actions: tuple[str, ...]
    verification_checks: tuple[str, ...]
    reactivation_requirements: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for field in (
            "ordered_actions", "verification_checks",
            "reactivation_requirements", "reason_codes",
        ):
            value[field] = list(value[field])
        return value


ORDERED_ACTIONS = (
    "DETACH_EXACT_AFFILIATE_WORKER_ROUTE",
    "VERIFY_PAGES_STATIC_SITE_STILL_SERVES",
    "VERIFY_AFFILIATE_PATH_FAILS_CLOSED",
    "PRESERVE_WORKER_VERSION_FOR_FORENSICS",
    "PRESERVE_D1_WITH_ZERO_NEW_ELIGIBILITY_CHANGES",
    "RECORD_SANITIZED_INCIDENT_SUMMARY",
)
VERIFICATION_CHECKS = (
    "AFFILIATE_ROUTE_NOT_ATTACHED",
    "AFFILIATE_PATH_HAS_NO_REDIRECT",
    "HOME_AND_INFORMATION_PAGES_AVAILABLE",
    "D1_SCHEMA_UNCHANGED",
    "SECRET_VALUES_NOT_READ_OR_EXPOSED",
    "NO_PAID_PLAN_OR_BILLING_CHANGE",
)
REACTIVATION_REQUIREMENTS = (
    "ROOT_CAUSE_IDENTIFIED",
    "FIX_REVIEWED_IN_PULL_REQUEST",
    "ALL_CI_AND_LOCAL_REGRESSION_PASS",
    "INERT_DEPLOYMENT_PREFLIGHT_PASS",
    "BLOCKED_PATH_PRODUCTION_SMOKE_PASS",
    "EXPLICIT_REACTIVATION_APPROVAL",
)


def build_plan() -> RollbackPlan:
    """Return instructions only; never call Cloudflare, Git, D1, or a shell."""

    try:
        if len(ORDERED_ACTIONS) != len(set(ORDERED_ACTIONS)):
            raise ValueError("duplicate action")
        if ORDERED_ACTIONS[0] != "DETACH_EXACT_AFFILIATE_WORKER_ROUTE":
            raise ValueError("unsafe order")
        if not all((ORDERED_ACTIONS, VERIFICATION_CHECKS, REACTIVATION_REQUIREMENTS)):
            raise ValueError("missing plan section")
        return RollbackPlan(
            PLAN_VERSION, READY, False, False, False,
            ORDERED_ACTIONS, VERIFICATION_CHECKS, REACTIVATION_REQUIREMENTS,
            ("SEPARATE_EXPLICIT_ROLLBACK_EXECUTION_REQUIRED",),
        )
    except Exception:
        return RollbackPlan(
            PLAN_VERSION, FAIL_CLOSED, False, False, False,
            (), (), (), ("ROLLBACK_PLAN_INTERNAL_ERROR",),
        )


def main() -> int:
    result = build_plan()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
