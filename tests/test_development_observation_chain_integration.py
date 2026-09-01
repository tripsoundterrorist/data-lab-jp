from dataclasses import replace
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import development_checkpoint_result_observation as checkpoint_adapter  # noqa: E402
import development_commit_push_result_observation as push_adapter  # noqa: E402
import development_gate_ci_observation as ci_adapter  # noqa: E402
import development_gate_coordinator as coordinator  # noqa: E402
import development_gate_evidence as evidence_core  # noqa: E402
import development_remote_iphone_approval_observation as approval_adapter  # noqa: E402
import development_test_result_observation as test_adapter  # noqa: E402
import unattended_checkpoint_storage as checkpoint_storage  # noqa: E402


CHECKPOINT = "a" * 64
SHA = "b" * 40
RUN_ID = 33521945860


def coordinate(evidence, action, adapter):
    return coordinator.DevelopmentGateCoordinator._for_test(
        {action: adapter}
    ).coordinate(evidence)


def checkpoint_result():
    return checkpoint_storage.CheckpointSaveResult(
        checkpoint_storage.CHECKPOINT_RESULT_VERSION,
        "SAVED",
        CHECKPOINT,
        ("CHECKPOINT_STORED",),
    )


def test_result(**changes):
    value = test_adapter.TestResultObservation(
        test_adapter.OBSERVATION_VERSION,
        test_adapter.SOURCE,
        CHECKPOINT,
        "FULL",
        "COMPLETED",
        "PASSED",
        2255,
        3,
        0,
        0,
    )
    return replace(value, **changes)


def push_result(**changes):
    value = push_adapter.CommitPushObservation(
        push_adapter.OBSERVATION_VERSION,
        push_adapter.SOURCE,
        push_adapter.APPROVED_REPOSITORY,
        push_adapter.APPROVED_REMOTE,
        "codex/gate-b",
        push_adapter.APPROVED_BASE,
        CHECKPOINT,
        "FULL",
        "COMPLETED",
        "PUSHED",
        SHA,
        SHA,
        False,
    )
    return replace(value, **changes)


def ci_result(**changes):
    value = ci_adapter.CIObservation(
        ci_adapter.OBSERVATION_VERSION,
        ci_adapter.SOURCE,
        ci_adapter.APPROVED_REPOSITORY,
        ci_adapter.APPROVED_WORKFLOW,
        "pull_request",
        ci_adapter.APPROVED_BASE,
        "codex/gate-b",
        CHECKPOINT,
        "FULL",
        SHA,
        "completed",
        "success",
        SHA,
        RUN_ID,
        (
            ci_adapter.CIJobObservation(
                "fast", "completed", "success", "FAST"
            ),
            ci_adapter.CIJobObservation(
                "validation", "completed", "success", "REGRESSION"
            ),
        ),
    )
    return replace(value, **changes)


def approval_result(**changes):
    value = approval_adapter.RemoteApprovalObservation(
        approval_adapter.OBSERVATION_VERSION,
        approval_adapter.APPROVED_SOURCE,
        approval_adapter.APPROVED_REPOSITORY,
        approval_adapter.APPROVED_DEVICE_CLASS,
        "approval-gate-b",
        "gate-a",
        "gate-b",
        SHA,
        RUN_ID,
        "APPROVED",
        1000,
        1010,
    )
    return replace(value, **changes)


class DevelopmentObservationChainIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.initial = evidence_core.DevelopmentGateEvidence("gate-a", "gate-b")

    def advance_to_ci(self):
        checkpointed = coordinate(
            self.initial,
            "SAVE_CHECKPOINT",
            lambda value: checkpoint_adapter.observe(value, checkpoint_result()),
        )
        self.assertEqual(checkpointed.after_status, "TEST_REQUIRED")

        checkpointed_evidence = replace(
            self.initial,
            checkpoint_status="SAVED",
            checkpoint_ref=CHECKPOINT,
        )
        tested = coordinate(
            checkpointed_evidence,
            "RUN_TESTS",
            lambda value: test_adapter.observe(value, test_result()),
        )
        self.assertEqual(tested.after_status, "COMMIT_PUSH_REQUIRED")

        pushed_input = replace(
            checkpointed_evidence,
            test_tier="FULL",
            test_status="PASSED",
        )
        pushed = coordinate(
            pushed_input,
            "COMMIT_AND_PUSH",
            lambda value: push_adapter.observe(value, push_result()),
        )
        self.assertEqual(pushed.after_status, "CI_REQUIRED")
        return replace(pushed_input, commit_sha=SHA, pushed_sha=SHA)

    def test_chain_reaches_approval_boundary_without_starting_next_gate(self):
        awaiting_ci = self.advance_to_ci()
        observed = coordinate(
            awaiting_ci,
            "WAIT_FOR_CI",
            lambda value: ci_adapter.observe(
                value, ci_result(), approval_required=True
            ),
        )
        self.assertEqual(
            (observed.status, observed.after_status, observed.next_gate_started),
            ("ACTION_COMPLETED", "APPROVAL_REQUIRED", False),
        )

    def test_iphone_approval_reaches_ready_but_does_not_start_gate(self):
        awaiting_ci = self.advance_to_ci()
        approved_input = replace(
            awaiting_ci,
            ci_status="SUCCESS",
            ci_head_sha=SHA,
            ci_run_id=RUN_ID,
            approval_status="REQUIRED",
        )
        approved = coordinate(
            approved_input,
            "REQUEST_APPROVAL",
            lambda value: approval_adapter.observe(
                value, approval_result(), evaluated_at_epoch_s=1011
            ),
        )
        self.assertEqual(
            (approved.status, approved.after_status, approved.next_gate_started),
            ("ACTION_COMPLETED", "NEXT_GATE_READY", False),
        )

    def test_checkpoint_mismatch_blocks_test_stage(self):
        checkpointed = replace(
            self.initial,
            checkpoint_status="SAVED",
            checkpoint_ref=CHECKPOINT,
        )
        result = coordinate(
            checkpointed,
            "RUN_TESTS",
            lambda value: test_adapter.observe(
                value, test_result(checkpoint_ref="c" * 64)
            ),
        )
        self.assertEqual(result.status, "ACTION_FAILED_SAFE")
        self.assertFalse(result.next_gate_started)

    def test_ci_ref_mismatch_blocks_at_ci_boundary(self):
        awaiting_ci = self.advance_to_ci()
        result = coordinate(
            awaiting_ci,
            "WAIT_FOR_CI",
            lambda value: ci_adapter.observe(
                value, ci_result(branch="main"), approval_required=True
            ),
        )
        self.assertEqual(result.status, "ACTION_FAILED_SAFE")
        self.assertFalse(result.next_gate_started)

    def test_approval_target_mismatch_remains_blocked(self):
        approved_input = replace(
            self.advance_to_ci(),
            ci_status="SUCCESS",
            ci_head_sha=SHA,
            ci_run_id=RUN_ID,
            approval_status="REQUIRED",
        )
        result = coordinate(
            approved_input,
            "REQUEST_APPROVAL",
            lambda value: approval_adapter.observe(
                value,
                approval_result(next_gate_id="gate-c"),
                evaluated_at_epoch_s=1011,
            ),
        )
        self.assertEqual(result.status, "ACTION_FAILED_SAFE")
        self.assertFalse(result.next_gate_started)


if __name__ == "__main__":
    unittest.main()
