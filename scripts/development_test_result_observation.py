"""Pure observation adapter for an already-completed test-tier result."""

from __future__ import annotations

from dataclasses import dataclass, replace

import development_gate_coordinator as coordinator
import development_gate_evidence as evidence_core


OBSERVATION_VERSION = "0.1"
SOURCE = "TEST_TIER_RUNNER"
_STATUSES = frozenset({"QUEUED", "IN_PROGRESS", "COMPLETED"})
_CONCLUSIONS = frozenset({"PASSED", "FAILED"})


@dataclass(frozen=True)
class TestResultObservation:
    observation_version: str
    source: str
    checkpoint_ref: str
    test_tier: str
    status: str
    conclusion: str | None
    test_count: int
    skipped_count: int
    failure_count: int
    error_count: int


def _action(
    status: str,
    evidence: evidence_core.DevelopmentGateEvidence | None,
    *reasons: str,
) -> coordinator.DevelopmentGateActionResult:
    return coordinator.DevelopmentGateActionResult(
        coordinator.ACTION_RESULT_VERSION,
        "RUN_TESTS",
        status,
        evidence,
        tuple(reasons),
    )


def _valid_counts(value: TestResultObservation) -> bool:
    counts = (
        value.test_count, value.skipped_count,
        value.failure_count, value.error_count,
    )
    return (
        all(type(count) is int and count >= 0 for count in counts) and
        value.test_count > 0 and value.skipped_count <= value.test_count and
        value.skipped_count + value.failure_count + value.error_count <=
        value.test_count
    )


def observe(
    evidence: object,
    observation: object,
) -> coordinator.DevelopmentGateActionResult:
    """Validate supplied test evidence; never run, poll, retry, or write."""
    decision = evidence_core.evaluate(evidence)
    if decision.status != "TEST_REQUIRED":
        return _action(
            coordinator.ACTION_FAILED, None,
            "TEST_OBSERVATION_NOT_EXPECTED",
        )
    if type(observation) is not TestResultObservation:
        return _action(
            coordinator.ACTION_FAILED, None,
            "TEST_OBSERVATION_INVALID",
        )
    if (observation.observation_version != OBSERVATION_VERSION or
            observation.source != SOURCE or
            observation.checkpoint_ref != evidence.checkpoint_ref or
            observation.test_tier not in evidence_core.TEST_TIERS or
            observation.status not in _STATUSES or
            not _valid_counts(observation)):
        return _action(
            coordinator.ACTION_FAILED, None,
            "TEST_OBSERVATION_INVALID",
        )
    if observation.status != "COMPLETED":
        if observation.conclusion is not None or any((
            observation.failure_count, observation.error_count,
        )):
            return _action(
                coordinator.ACTION_FAILED, None,
                "TEST_OBSERVATION_INVALID",
            )
        return _action(
            coordinator.ACTION_UNCERTAIN, None,
            "TEST_RUN_NOT_COMPLETED",
        )
    if observation.conclusion not in _CONCLUSIONS:
        return _action(
            coordinator.ACTION_FAILED, None,
            "TEST_OBSERVATION_INVALID",
        )
    passed = (
        observation.conclusion == "PASSED" and
        observation.failure_count == 0 and observation.error_count == 0
    )
    failed = (
        observation.conclusion == "FAILED" and
        observation.failure_count + observation.error_count > 0
    )
    if not passed and not failed:
        return _action(
            coordinator.ACTION_FAILED, None,
            "TEST_OBSERVATION_CONTRADICTORY",
        )
    if failed:
        return _action(
            coordinator.ACTION_FAILED, None,
            "TEST_RUN_FAILED",
        )

    assert isinstance(evidence, evidence_core.DevelopmentGateEvidence)
    updated = replace(
        evidence,
        test_tier=observation.test_tier,
        test_status="PASSED",
    )
    return _action(
        coordinator.ACTION_SUCCEEDED, updated,
        "TEST_RESULT_VALIDATED",
    )


__all__ = ["OBSERVATION_VERSION", "SOURCE", "TestResultObservation", "observe"]
