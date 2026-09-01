"""Pure observation adapter for an already-completed commit and push."""

from __future__ import annotations

from dataclasses import dataclass, replace
import re

import development_gate_coordinator as coordinator
import development_gate_evidence as evidence_core


OBSERVATION_VERSION = "0.1"
SOURCE = "GIT_REMOTE_OBSERVER"
APPROVED_REPOSITORY = "tripsoundterrorist/data-lab-jp"
APPROVED_REMOTE = "origin"
APPROVED_BASE = "main"
_BRANCH = re.compile(r"codex/[a-z0-9][a-z0-9._/-]{0,120}\Z")
_STATUSES = frozenset({"QUEUED", "IN_PROGRESS", "COMPLETED"})
_CONCLUSIONS = frozenset({"PUSHED", "FAILED"})


@dataclass(frozen=True)
class CommitPushObservation:
    observation_version: str
    source: str
    repository: str
    remote: str
    branch: str
    base_branch: str
    checkpoint_ref: str
    test_tier: str
    status: str
    conclusion: str | None
    commit_sha: str | None
    pushed_sha: str | None
    force_push: bool


def _action(
    status: str,
    evidence: evidence_core.DevelopmentGateEvidence | None,
    *reasons: str,
) -> coordinator.DevelopmentGateActionResult:
    return coordinator.DevelopmentGateActionResult(
        coordinator.ACTION_RESULT_VERSION,
        "COMMIT_AND_PUSH",
        status,
        evidence,
        tuple(reasons),
    )


def _valid_sha(value: object) -> bool:
    return (
        type(value) is str and
        evidence_core.COMMIT_SHA.fullmatch(value) is not None
    )


def _valid_branch(value: object) -> bool:
    if (type(value) is not str or _BRANCH.fullmatch(value) is None or
            ".." in value or "//" in value or value.endswith(("/", "."))):
        return False
    return all(
        part and not part.startswith(".") and not part.endswith(".lock")
        for part in value.split("/")
    )


def observe(
    evidence: object,
    observation: object,
) -> coordinator.DevelopmentGateActionResult:
    """Validate supplied Git evidence; never commit, push, poll, or write."""
    decision = evidence_core.evaluate(evidence)
    if decision.status != "COMMIT_PUSH_REQUIRED":
        return _action(
            coordinator.ACTION_FAILED, None,
            "COMMIT_PUSH_OBSERVATION_NOT_EXPECTED",
        )
    if type(observation) is not CommitPushObservation:
        return _action(
            coordinator.ACTION_FAILED, None,
            "COMMIT_PUSH_OBSERVATION_INVALID",
        )
    if (observation.observation_version != OBSERVATION_VERSION or
            observation.source != SOURCE or
            observation.repository != APPROVED_REPOSITORY or
            observation.remote != APPROVED_REMOTE or
            observation.base_branch != APPROVED_BASE or
            not _valid_branch(observation.branch) or
            observation.checkpoint_ref != evidence.checkpoint_ref or
            observation.test_tier != evidence.test_tier or
            observation.status not in _STATUSES or
            type(observation.force_push) is not bool or observation.force_push or
            (observation.commit_sha is not None and
             not _valid_sha(observation.commit_sha)) or
            (observation.pushed_sha is not None and
             not _valid_sha(observation.pushed_sha))):
        return _action(
            coordinator.ACTION_FAILED, None,
            "COMMIT_PUSH_OBSERVATION_INVALID",
        )

    if observation.status != "COMPLETED":
        if (observation.conclusion is not None or
                observation.pushed_sha is not None or
                (observation.commit_sha is not None and
                 not _valid_sha(observation.commit_sha))):
            return _action(
                coordinator.ACTION_FAILED, None,
                "COMMIT_PUSH_OBSERVATION_INVALID",
            )
        return _action(
            coordinator.ACTION_UNCERTAIN, None,
            "COMMIT_PUSH_NOT_COMPLETED",
        )

    if observation.conclusion not in _CONCLUSIONS:
        return _action(
            coordinator.ACTION_FAILED, None,
            "COMMIT_PUSH_OBSERVATION_INVALID",
        )
    if observation.conclusion == "FAILED":
        if observation.pushed_sha is not None:
            return _action(
                coordinator.ACTION_FAILED, None,
                "COMMIT_PUSH_OBSERVATION_CONTRADICTORY",
            )
        return _action(
            coordinator.ACTION_FAILED, None,
            "COMMIT_PUSH_FAILED",
        )
    if (not _valid_sha(observation.commit_sha) or
            observation.pushed_sha != observation.commit_sha):
        return _action(
            coordinator.ACTION_FAILED, None,
            "COMMIT_PUSH_SHA_MISMATCH",
        )

    assert isinstance(evidence, evidence_core.DevelopmentGateEvidence)
    updated = replace(
        evidence,
        commit_sha=observation.commit_sha,
        pushed_sha=observation.pushed_sha,
    )
    return _action(
        coordinator.ACTION_SUCCEEDED, updated,
        "COMMIT_PUSH_RESULT_VALIDATED",
    )


__all__ = [
    "APPROVED_BASE", "APPROVED_REMOTE", "APPROVED_REPOSITORY",
    "CommitPushObservation", "OBSERVATION_VERSION", "SOURCE", "observe",
]
