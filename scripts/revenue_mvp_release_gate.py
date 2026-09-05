"""One-command, non-deploying Revenue MVP release readiness gate."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import publication_readiness
import revenue_mvp_deployment_preflight
import revenue_mvp_official_answer_matrix
import revenue_mvp_search_console_gate


GATE_VERSION = "0.3"
READY_FOR_RELEASE_APPROVAL = "READY_FOR_RELEASE_APPROVAL"
BLOCKED = "BLOCKED"
FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class ReleaseGateResult:
    gate_version: str
    status: str
    production_release_allowed: bool
    shell_status: str
    search_console_status: str
    public_shell_indexing_allowed: bool
    official_answer_status: str
    core_official_answer_candidate: bool
    sns_official_answer_candidate: bool
    official_answer_gate_unlock_allowed: bool
    public_data_state: str
    public_data_deployment_allowed: bool
    publication_readiness: str
    affiliate_integration_allowed: bool
    reason_codes: tuple[str, ...]
    next_actions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        value["next_actions"] = list(self.next_actions)
        return value


def run_gate(*, artifact_directory: Path | None = None) -> ReleaseGateResult:
    """Aggregate safe summaries only; never build, publish, or expose URLs."""

    try:
        deployment = revenue_mvp_deployment_preflight.run_preflight(
            artifact_directory=artifact_directory
        )
        publication = publication_readiness.build_report(
            publication_readiness.current_input(),
            generated_at=datetime.now(timezone.utc),
        )
        search_console = revenue_mvp_search_console_gate.run_gate()
        official_answers = revenue_mvp_official_answer_matrix.assess_answer_matrix(
            revenue_mvp_official_answer_matrix.current_entries()
        )
        ready = (
            deployment.status == revenue_mvp_deployment_preflight.READY
            and deployment.public_data_deployment_allowed is True
            and publication.overall_readiness == publication_readiness.READY
            and publication.overall_eligible is True
            and search_console.status == revenue_mvp_search_console_gate.READY
            and search_console.public_shell_indexing_allowed is True
            and official_answers.core_publication_candidate is True
        )
        reasons = (
            set(deployment.reason_codes)
            | set(publication.reason_codes)
            | set(search_console.reason_codes)
            | set(official_answers.reason_codes)
        )
        if not ready:
            reasons.add("REVENUE_MVP_RELEASE_BLOCKED")
        return ReleaseGateResult(
            GATE_VERSION,
            READY_FOR_RELEASE_APPROVAL if ready else BLOCKED,
            False,  # A separate explicit approval is always required.
            deployment.status,
            search_console.status,
            search_console.public_shell_indexing_allowed,
            official_answers.status,
            official_answers.core_publication_candidate,
            official_answers.sns_operation_candidate,
            official_answers.gate_unlock_allowed,
            deployment.public_data_state,
            deployment.public_data_deployment_allowed,
            publication.overall_readiness,
            ready,
            tuple(sorted(reasons)),
            tuple(dict.fromkeys(
                publication.next_actions
                + search_console.next_actions
                + (() if official_answers.core_publication_candidate else ("WAIT_FOR_DMM_FANZA_OFFICIAL_RESPONSE",))
            )),
        )
    except Exception:
        return ReleaseGateResult(
            GATE_VERSION, FAIL_CLOSED, False, "UNKNOWN", "UNKNOWN", False,
            "UNKNOWN", False, False, False,
            "UNKNOWN", False,
            publication_readiness.FAIL_CLOSED, False,
            ("RELEASE_GATE_INTERNAL_ERROR",), (),
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report Revenue MVP release readiness without deploying."
    )
    parser.add_argument("--artifact-dir", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_gate(artifact_directory=args.artifact_dir)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status in {BLOCKED, READY_FOR_RELEASE_APPROVAL} else 2


if __name__ == "__main__":
    raise SystemExit(main())
