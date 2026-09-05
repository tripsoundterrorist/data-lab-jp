"""Prioritized, read-only checklist for unblocking the Revenue MVP."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

import revenue_mvp_db_handoff_preflight
import revenue_mvp_release_gate


VERSION = "0.1"
READY = "READY_FOR_FINAL_RELEASE_GATE"
BLOCKED = "BLOCKED"
FAIL_CLOSED = "FAIL_CLOSED"
NOT_PROVIDED = "NOT_PROVIDED"


@dataclass(frozen=True)
class UnlockChecklistResult:
    version: str
    status: str
    production_release_allowed: bool
    db_handoff_status: str
    db_identity_verified: bool
    release_gate_status: str
    production_smoke_status: str
    official_answer_status: str
    core_official_answer_candidate: bool
    public_data_deployment_allowed: bool
    publication_readiness: str
    search_console_status: str
    ordered_blockers: tuple[str, ...]
    next_action: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["ordered_blockers"] = list(self.ordered_blockers)
        return value


def build_checklist(
    release: revenue_mvp_release_gate.ReleaseGateResult,
    db_handoff: revenue_mvp_db_handoff_preflight.HandoffResult | None,
) -> UnlockChecklistResult:
    """Convert existing Gate summaries into one stable priority order."""

    blockers: list[str] = []
    db_status = NOT_PROVIDED if db_handoff is None else db_handoff.status
    db_verified = bool(db_handoff and db_handoff.identity_verified)
    if db_handoff is None:
        blockers.append("PROVIDE_ORIGINAL_DB_AND_SHA256")
    elif (
        db_handoff.status != revenue_mvp_db_handoff_preflight.READY
        or not db_handoff.identity_verified
    ):
        blockers.append("FIX_DB_HANDOFF_PREFLIGHT")
    if not release.core_official_answer_candidate:
        blockers.append("WAIT_FOR_DMM_FANZA_CORE_RESPONSE")
    if release.production_smoke_status != "PRODUCTION_SHELL_VALIDATED":
        blockers.append("RESTORE_PRODUCTION_SHELL")
    if release.search_console_status != "PUBLIC_SHELL_READY":
        blockers.append("FIX_SEARCH_CONSOLE_GATE")
    if not release.public_data_deployment_allowed:
        blockers.append("PREPARE_VALIDATED_PUBLIC_DATA_ARTIFACT")
    if release.publication_readiness != "READY":
        blockers.append("COMPLETE_PUBLICATION_READINESS")
    if release.status == revenue_mvp_release_gate.FAIL_CLOSED:
        blockers.append("FIX_RELEASE_GATE_INTERNAL_FAILURE")

    ready = not blockers and release.status == revenue_mvp_release_gate.READY_FOR_RELEASE_APPROVAL
    if not ready and not blockers:
        blockers.append("REVIEW_RELEASE_GATE_BLOCKERS")
    return UnlockChecklistResult(
        VERSION,
        READY if ready else BLOCKED,
        False,
        db_status,
        db_verified,
        release.status,
        release.production_smoke_status,
        release.official_answer_status,
        release.core_official_answer_candidate,
        release.public_data_deployment_allowed,
        release.publication_readiness,
        release.search_console_status,
        tuple(blockers),
        "REQUEST_FINAL_RELEASE_APPROVAL" if ready else blockers[0],
    )


def run_checklist(
    *, db_path: Path | None = None, expected_sha256: str | None = None,
    artifact_directory: Path | None = None,
) -> UnlockChecklistResult:
    """Run existing read-only Gates; never deploy or mutate the supplied DB."""

    try:
        if (db_path is None) != (expected_sha256 is None):
            raise ValueError("DB path and expected SHA-256 must be supplied together")
        db_handoff = None
        if db_path is not None and expected_sha256 is not None:
            db_handoff = revenue_mvp_db_handoff_preflight.preflight(
                db_path, expected_sha256
            )
        release = revenue_mvp_release_gate.run_gate(
            artifact_directory=artifact_directory
        )
        return build_checklist(release, db_handoff)
    except Exception:
        return UnlockChecklistResult(
            VERSION, FAIL_CLOSED, False, "UNKNOWN", False, "UNKNOWN",
            "UNKNOWN", "UNKNOWN", False, False, "UNKNOWN", "UNKNOWN",
            ("UNLOCK_CHECKLIST_INTERNAL_ERROR",),
            "FIX_UNLOCK_CHECKLIST_INTERNAL_FAILURE",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report prioritized Revenue MVP blockers without writes."
    )
    parser.add_argument("--db", type=Path)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--artifact-dir", type=Path)
    args = parser.parse_args(argv)
    result = run_checklist(
        db_path=args.db,
        expected_sha256=args.expected_sha256,
        artifact_directory=args.artifact_dir,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {READY, BLOCKED} else 2


if __name__ == "__main__":
    raise SystemExit(main())
