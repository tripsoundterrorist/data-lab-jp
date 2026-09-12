"""Offline rehearsal of the post-response Revenue MVP activation path."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
from typing import Any

import official_blocker_policy
import revenue_mvp_activation_runbook


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1"
PASS = "OFFLINE_LAUNCH_REHEARSAL_PASS"
BLOCKED = "OFFLINE_LAUNCH_REHEARSAL_BLOCKED"
CHECKS_REQUIRED = 5


@dataclass(frozen=True)
class LaunchRehearsalResult:
    version: str
    status: str
    checks_passed: int
    checks_required: int
    future_gate_path_verified: bool
    d1_enable_and_rollback_verified: bool
    worker_redirect_candidate_verified: bool
    activation_order_verified: bool
    production_write_performed: bool
    network_request_performed: bool
    deploy_allowed: bool
    paid_plan_change_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _future_gate_path() -> bool:
    statuses = {
        "RIGHTS_GATE": "PASS",
        "LIFECYCLE_GATE": "PASS",
        "SEMANTICS_GATE": "PASS",
        "DATA_POLICY_GATE": "PASS",
        "ARTIFACT_VALIDATION": "PASS",
        "PRODUCTION_BUILD": "PASS",
        "DEPLOYMENT_PREFLIGHT": "PASS",
    }
    return official_blocker_policy.publication_activation_allowed(
        statuses, explicit_internal_approval=True
    )


def _d1_rehearsal() -> tuple[bool, bool]:
    schema = (ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql").read_text(
        encoding="utf-8"
    )
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(schema)
        connection.execute(
            """INSERT INTO affiliate_item_lookup (
                   public_id, content_id, rights_status, lifecycle_status,
                   verification_status, affiliate_enabled, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "itm_0123456789abcdef01234567",
                "fixture-content",
                "CONDITIONALLY_APPROVED",
                "RESOLVED",
                "PASS",
                1,
                "2026-09-12T00:00:00Z",
            ),
        )
        enabled = connection.execute(
            "SELECT count(*) FROM affiliate_runtime_eligible_lookup"
        ).fetchone()[0]
        connection.execute("UPDATE affiliate_item_lookup SET affiliate_enabled = 0")
        rolled_back = connection.execute(
            "SELECT count(*) FROM affiliate_runtime_eligible_lookup"
        ).fetchone()[0]
        return enabled == 1, rolled_back == 0
    finally:
        connection.close()


def _worker_rehearsal() -> bool:
    node = shutil.which("node")
    if node is None:
        return False
    completed = subprocess.run(
        [node, str(ROOT / "tests" / "affiliate_pages_entrypoint_candidate_harness.mjs")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return completed.returncode == 0


def run_rehearsal() -> LaunchRehearsalResult:
    try:
        gate = _future_gate_path()
        enabled, rolled_back = _d1_rehearsal()
        worker = _worker_rehearsal()
        order = (
            revenue_mvp_activation_runbook.ORDERED_STEPS[0]
            == "INTAKE_AND_CLASSIFY_DMM_RESPONSE"
            and revenue_mvp_activation_runbook.ROLLBACK_ORDER[0]
            == "CLOSE_WORKER_RELEASE_FACTS"
            and revenue_mvp_activation_runbook.ROLLBACK_ORDER[-1]
            == "RUN_BLOCKED_ROUTE_AND_SHELL_SMOKE"
        )
        checks = (gate, enabled, rolled_back, worker, order)
        passed = sum(checks)
        ready = passed == CHECKS_REQUIRED
        return LaunchRehearsalResult(
            VERSION, PASS if ready else BLOCKED, passed, CHECKS_REQUIRED,
            gate, enabled and rolled_back, worker, order,
            False, False, False, False,
            (
                "POST_RESPONSE_PATH_REHEARSED_OFFLINE",
                "REAL_ACTIVATION_REQUIRES_FRESH_EVIDENCE_AND_APPROVAL",
            ) if ready else ("OFFLINE_REHEARSAL_INCOMPLETE",),
        )
    except Exception:
        return LaunchRehearsalResult(
            VERSION, BLOCKED, 0, CHECKS_REQUIRED,
            False, False, False, False, False, False, False, False,
            ("OFFLINE_REHEARSAL_ERROR",),
        )


def main() -> int:
    result = run_rehearsal()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
