"""Pure fail-closed evidence contract for automated development Gates."""

from __future__ import annotations

from dataclasses import dataclass
import re


CONTRACT_VERSION = "0.1"
GATE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
CHECKPOINT_REF = re.compile(r"[0-9a-f]{64}\Z")
COMMIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
TEST_TIERS = frozenset({"FAST", "REGRESSION", "FULL"})
DURABLE_CHECKPOINT_STATUSES = frozenset({"SAVED", "NO_CHANGE"})
APPROVAL_STATUSES = frozenset({"NOT_REQUIRED", "REQUIRED", "APPROVED", "DENIED"})


@dataclass(frozen=True)
class DevelopmentGateEvidence:
    current_gate_id: str
    next_gate_id: str
    checkpoint_status: str | None = None
    checkpoint_ref: str | None = None
    test_tier: str | None = None
    test_status: str | None = None
    commit_sha: str | None = None
    pushed_sha: str | None = None
    ci_status: str | None = None
    ci_head_sha: str | None = None
    ci_run_id: int | None = None
    approval_status: str | None = None


@dataclass(frozen=True)
class DevelopmentGateDecision:
    contract_version: str
    status: str
    next_action: str
    next_gate_allowed: bool
    reason_codes: tuple[str, ...]


def _decision(status: str, action: str, allowed: bool,
              *reasons: str) -> DevelopmentGateDecision:
    return DevelopmentGateDecision(
        CONTRACT_VERSION, status, action, allowed, tuple(reasons)
    )


def _valid_gate_id(value: object) -> bool:
    return type(value) is str and GATE_ID.fullmatch(value) is not None


def _invalid(*reasons: str) -> DevelopmentGateDecision:
    return _decision("EVIDENCE_REJECTED", "NONE", False, *reasons)


def evaluate(value: object) -> DevelopmentGateDecision:
    """Return the only safe next action; perform no I/O or mutation."""
    if not isinstance(value, DevelopmentGateEvidence):
        return _invalid("EVIDENCE_TYPE_INVALID")
    if not _valid_gate_id(value.current_gate_id) or not _valid_gate_id(value.next_gate_id):
        return _invalid("GATE_ID_INVALID")
    if value.current_gate_id == value.next_gate_id:
        return _invalid("NEXT_GATE_NOT_DISTINCT")

    if value.checkpoint_status is None and value.checkpoint_ref is None:
        return _decision("CHECKPOINT_REQUIRED", "SAVE_CHECKPOINT", False,
                         "DURABLE_CHECKPOINT_EVIDENCE_REQUIRED")
    if value.checkpoint_status not in DURABLE_CHECKPOINT_STATUSES:
        return _invalid("CHECKPOINT_NOT_DURABLE")
    if type(value.checkpoint_ref) is not str or CHECKPOINT_REF.fullmatch(
            value.checkpoint_ref) is None:
        return _invalid("CHECKPOINT_REFERENCE_INVALID")

    if value.test_status is None and value.test_tier is None:
        return _decision("TEST_REQUIRED", "RUN_TESTS", False,
                         "TEST_EVIDENCE_REQUIRED")
    if value.test_tier not in TEST_TIERS:
        return _invalid("TEST_TIER_INVALID")
    if value.test_status != "PASSED":
        return _invalid("TESTS_NOT_PASSED")

    if value.commit_sha is None and value.pushed_sha is None:
        return _decision("COMMIT_PUSH_REQUIRED", "COMMIT_AND_PUSH", False,
                         "COMMIT_PUSH_EVIDENCE_REQUIRED")
    if type(value.commit_sha) is not str or COMMIT_SHA.fullmatch(value.commit_sha) is None:
        return _invalid("COMMIT_SHA_INVALID")
    if value.pushed_sha != value.commit_sha:
        return _invalid("PUSHED_SHA_MISMATCH")

    if value.ci_status is None and value.ci_head_sha is None and value.ci_run_id is None:
        return _decision("CI_REQUIRED", "WAIT_FOR_CI", False,
                         "CI_SUCCESS_EVIDENCE_REQUIRED")
    if value.ci_status != "SUCCESS":
        return _invalid("CI_NOT_SUCCESSFUL")
    if value.ci_head_sha != value.commit_sha:
        return _invalid("CI_HEAD_SHA_MISMATCH")
    if type(value.ci_run_id) is not int or value.ci_run_id <= 0:
        return _invalid("CI_RUN_ID_INVALID")

    if value.approval_status not in APPROVAL_STATUSES:
        return _invalid("APPROVAL_STATUS_INVALID")
    if value.approval_status == "REQUIRED":
        return _decision("APPROVAL_REQUIRED", "REQUEST_APPROVAL", False,
                         "NEXT_GATE_APPROVAL_REQUIRED")
    if value.approval_status == "DENIED":
        return _invalid("NEXT_GATE_APPROVAL_DENIED")
    return _decision("NEXT_GATE_READY", "START_NEXT_GATE", True,
                     "DEVELOPMENT_GATE_EVIDENCE_COMPLETE")


__all__ = [
    "CONTRACT_VERSION", "DevelopmentGateDecision", "DevelopmentGateEvidence",
    "evaluate",
]
