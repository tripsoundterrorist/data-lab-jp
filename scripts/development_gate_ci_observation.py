"""Pure read-only GitHub Actions observation adapter."""

from __future__ import annotations

from dataclasses import dataclass, replace
import re

import development_gate_coordinator as coordinator
import development_gate_evidence as evidence_core


OBSERVATION_VERSION = "0.2"
SOURCE = "GITHUB_ACTIONS"
APPROVED_REPOSITORY = "tripsoundterrorist/data-lab-jp"
APPROVED_WORKFLOW = "CI"
APPROVED_BASE = "main"
_BRANCH = re.compile(r"codex/[a-z0-9][a-z0-9._/-]{0,120}\Z")
_STATUSES = frozenset({"queued", "in_progress", "completed"})


@dataclass(frozen=True)
class CIJobObservation:
    name: str
    status: str
    conclusion: str | None
    validation_tier: str | None = None


@dataclass(frozen=True)
class CIObservation:
    observation_version: str
    source: str
    repository: str
    workflow_name: str
    event: str
    base_branch: str
    branch: str
    checkpoint_ref: str
    test_tier: str
    pushed_sha: str
    status: str
    conclusion: str | None
    head_sha: str
    run_id: int
    jobs: tuple[CIJobObservation, ...]


def _action(status: str, updated: evidence_core.DevelopmentGateEvidence | None,
            *reasons: str) -> coordinator.DevelopmentGateActionResult:
    return coordinator.DevelopmentGateActionResult(
        coordinator.ACTION_RESULT_VERSION, "WAIT_FOR_CI", status, updated,
        tuple(reasons),
    )


def _valid_feature_branch(value: object) -> bool:
    if (type(value) is not str or _BRANCH.fullmatch(value) is None or
            ".." in value or "//" in value or value.endswith(("/", "."))):
        return False
    return all(
        part and not part.startswith(".") and not part.endswith(".lock")
        for part in value.split("/")
    )


def observe(evidence: object, observation: object, *,
            approval_required: bool) -> coordinator.DevelopmentGateActionResult:
    """Validate a supplied snapshot; never fetch, poll, retry, or write."""
    decision = evidence_core.evaluate(evidence)
    if decision.status != "CI_REQUIRED":
        return _action(coordinator.ACTION_FAILED, None, "CI_OBSERVATION_NOT_EXPECTED")
    if type(approval_required) is not bool:
        return _action(coordinator.ACTION_FAILED, None, "APPROVAL_POLICY_INVALID")
    if type(observation) is not CIObservation:
        return _action(coordinator.ACTION_FAILED, None, "CI_OBSERVATION_INVALID")
    if (observation.observation_version != OBSERVATION_VERSION or
            observation.source != SOURCE or
            observation.repository != APPROVED_REPOSITORY or
            observation.workflow_name != APPROVED_WORKFLOW or
            observation.event not in {"pull_request", "push"} or
            observation.base_branch != APPROVED_BASE or
            observation.checkpoint_ref != evidence.checkpoint_ref or
            observation.test_tier != evidence.test_tier or
            observation.pushed_sha != evidence.pushed_sha or
            observation.status not in _STATUSES):
        return _action(coordinator.ACTION_FAILED, None, "CI_IDENTITY_INVALID")
    if observation.event == "pull_request":
        if not _valid_feature_branch(observation.branch):
            return _action(coordinator.ACTION_FAILED, None, "CI_REF_INVALID")
    elif observation.branch != APPROVED_BASE:
        return _action(coordinator.ACTION_FAILED, None, "CI_REF_INVALID")
    if (observation.head_sha != evidence.commit_sha or
            observation.head_sha != evidence.pushed_sha):
        return _action(coordinator.ACTION_FAILED, None, "CI_HEAD_SHA_MISMATCH")
    if type(observation.run_id) is not int or observation.run_id <= 0:
        return _action(coordinator.ACTION_FAILED, None, "CI_RUN_ID_INVALID")
    if observation.status != "completed":
        if observation.conclusion is not None:
            return _action(
                coordinator.ACTION_FAILED, None, "CI_OBSERVATION_CONTRADICTORY"
            )
        return _action(coordinator.ACTION_UNCERTAIN, None, "CI_NOT_COMPLETED")
    if observation.conclusion != "success":
        return _action(coordinator.ACTION_FAILED, None, "CI_NOT_SUCCESSFUL")
    if (type(observation.jobs) is not tuple or len(observation.jobs) != 2 or
            not all(type(job) is CIJobObservation for job in observation.jobs)):
        return _action(coordinator.ACTION_FAILED, None, "CI_JOBS_INVALID")

    jobs = {job.name: job for job in observation.jobs}
    if set(jobs) != {"fast", "validation"}:
        return _action(coordinator.ACTION_FAILED, None, "CI_JOBS_INVALID")
    if any(job.status != "completed" or job.conclusion != "success"
           for job in jobs.values()):
        return _action(coordinator.ACTION_FAILED, None, "CI_JOB_NOT_SUCCESSFUL")
    expected_tier = "REGRESSION" if observation.event == "pull_request" else "FULL"
    if jobs["fast"].validation_tier != "FAST" or \
            jobs["validation"].validation_tier != expected_tier:
        return _action(coordinator.ACTION_FAILED, None, "CI_TIER_EVIDENCE_INVALID")

    updated = replace(
        evidence,
        ci_status="SUCCESS",
        ci_head_sha=observation.head_sha,
        ci_run_id=observation.run_id,
        approval_status="REQUIRED" if approval_required else "NOT_REQUIRED",
    )
    return _action(coordinator.ACTION_SUCCEEDED, updated,
                   "CI_OBSERVATION_VALIDATED")


__all__ = [
    "APPROVED_BASE", "APPROVED_REPOSITORY", "APPROVED_WORKFLOW",
    "CIJobObservation", "CIObservation", "OBSERVATION_VERSION", "SOURCE",
    "observe",
]
