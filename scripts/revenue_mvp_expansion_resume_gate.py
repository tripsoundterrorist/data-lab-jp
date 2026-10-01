"""Read-only gate for resuming expansion batch preparation after Cron review."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

import revenue_mvp_cloudflare_dashboard_observation as dashboard
import revenue_mvp_revalidation_cadence_guard as cadence


VERSION = "0.1"
READY = "READY_FOR_NEXT_BATCH_PREPARATION"
BLOCKED = "EXPANSION_RESUME_BLOCKED"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXPORT = cadence.DEFAULT_EXPORT
DEFAULT_DASHBOARD_OBSERVATION = (
    ROOT / "runtime/evidence/revenue-mvp-cloudflare-dashboard-observation.json"
)


@dataclass(frozen=True)
class ResumeGate:
    version: str
    status: str
    historical_cadence_detected: bool
    current_dashboard_capacity_verified: bool
    unexpected_cron_absent: bool
    historical_cadence_accounted_for: bool
    next_batch_preparation_allowed: bool
    live_execution_allowed: bool
    production_write_allowed: bool
    explicit_live_approval_required: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def assess(cadence_result: Any, dashboard_result: Any) -> ResumeGate:
    cadence_valid = isinstance(cadence_result, cadence.CadenceGuardResult)
    dashboard_valid = isinstance(dashboard_result, dashboard.DashboardObservation)
    historical = cadence_valid and cadence_result.hourly_sequence_count > 0
    capacity = (
        dashboard_valid
        and dashboard_result.status == dashboard.VERIFIED
        and dashboard_result.cloudflare_free_plan_capacity_verified is True
    )
    cron_absent = capacity and dashboard_result.unexpected_cron_absent is True
    accounted = historical and cron_absent
    reasons: set[str] = set()
    if not cadence_valid or cadence_result.status == cadence.FAIL_CLOSED:
        reasons.add("CADENCE_EVIDENCE_INVALID")
    if not capacity:
        reasons.add("CURRENT_CLOUDFLARE_OBSERVATION_UNVERIFIED")
    if not cron_absent:
        reasons.add("UNEXPECTED_CRON_NOT_CLEARED")
    if historical and not accounted:
        reasons.add("HISTORICAL_CADENCE_UNACCOUNTED_FOR")
    if cadence_valid and cadence_result.status == cadence.BLOCKED and not historical:
        reasons.add("CADENCE_BLOCK_UNACCOUNTED_FOR")

    ready = not reasons
    return ResumeGate(
        VERSION, READY if ready else BLOCKED, historical, capacity, cron_absent,
        accounted, ready, False, False, True, tuple(sorted(reasons)),
    )


def current_gate(
    export_path: Path = DEFAULT_EXPORT,
    observation_path: Path = DEFAULT_DASHBOARD_OBSERVATION,
) -> ResumeGate:
    try:
        with export_path.open("r", encoding="utf-8", newline="") as source:
            cadence_result = cadence.assess(cadence.parse_export(source))
    except (OSError, UnicodeError, ValueError):
        cadence_result = cadence.assess(None)
    try:
        payload = json.loads(observation_path.read_text(encoding="utf-8"))
        dashboard_result = dashboard.validate(payload)
    except (OSError, UnicodeError, json.JSONDecodeError):
        dashboard_result = dashboard.validate(None)
    return assess(cadence_result, dashboard_result)


def main() -> int:
    result = current_gate()
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
