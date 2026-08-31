from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import development_gate_coordinator as coordinator  # noqa: E402
import development_gate_evidence as evidence  # noqa: E402


CHECKPOINT = "a" * 64
SHA = "b" * 40


def value(**changes):
    base = evidence.DevelopmentGateEvidence("gate-a", "gate-b")
    return replace(base, **changes)


def action(name, updated=None, status=coordinator.ACTION_SUCCEEDED):
    return coordinator.DevelopmentGateActionResult(
        coordinator.ACTION_RESULT_VERSION, name, status, updated
    )


class DevelopmentGateCoordinatorTests(unittest.TestCase):
    def test_default_is_disabled_and_invokes_nothing(self):
        adapter = mock.Mock(side_effect=AssertionError)
        actual = coordinator.DevelopmentGateCoordinator({"SAVE_CHECKPOINT": adapter}).coordinate(
            value()
        )
        self.assertEqual(actual.status, "AUTOMATION_DISABLED")
        self.assertFalse(actual.action_invoked)
        adapter.assert_not_called()

    def test_invalid_evidence_rejected_before_adapter(self):
        adapter = mock.Mock(side_effect=AssertionError)
        actual = coordinator.DevelopmentGateCoordinator._for_test(
            {"SAVE_CHECKPOINT": adapter}
        ).coordinate({})
        self.assertEqual(actual.status, "COORDINATION_REJECTED")
        adapter.assert_not_called()

    def test_missing_adapter_blocks_without_fallback(self):
        actual = coordinator.DevelopmentGateCoordinator._for_test({}).coordinate(value())
        self.assertEqual(actual.status, "COORDINATION_BLOCKED")
        self.assertFalse(actual.action_invoked)

    def test_checkpoint_action_advances_exactly_one_stage(self):
        updated = value(checkpoint_status="SAVED", checkpoint_ref=CHECKPOINT)
        adapter = mock.Mock(return_value=action("SAVE_CHECKPOINT", updated))
        actual = coordinator.DevelopmentGateCoordinator._for_test(
            {"SAVE_CHECKPOINT": adapter}
        ).coordinate(value())
        self.assertEqual((actual.status, actual.before_status, actual.after_status),
                         ("ACTION_COMPLETED", "CHECKPOINT_REQUIRED", "TEST_REQUIRED"))
        adapter.assert_called_once()

    def test_skip_ahead_is_rejected(self):
        complete = value(
            checkpoint_status="SAVED", checkpoint_ref=CHECKPOINT,
            test_tier="FULL", test_status="PASSED", commit_sha=SHA,
            pushed_sha=SHA, ci_status="SUCCESS", ci_head_sha=SHA,
            ci_run_id=1, approval_status="NOT_REQUIRED",
        )
        adapter = mock.Mock(return_value=action("SAVE_CHECKPOINT", complete))
        actual = coordinator.DevelopmentGateCoordinator._for_test(
            {"SAVE_CHECKPOINT": adapter}
        ).coordinate(value())
        self.assertEqual(actual.status, "ACTION_FAILED_SAFE")
        self.assertIn("ACTION_PROGRESS_INVALID", actual.reason_codes)

    def test_uncertain_is_not_retried(self):
        adapter = mock.Mock(return_value=action(
            "SAVE_CHECKPOINT", None, coordinator.ACTION_UNCERTAIN
        ))
        actual = coordinator.DevelopmentGateCoordinator._for_test(
            {"SAVE_CHECKPOINT": adapter}
        ).coordinate(value())
        self.assertEqual(actual.status, "ACTION_UNCERTAIN")
        adapter.assert_called_once()

    def test_failure_is_not_retried(self):
        adapter = mock.Mock(return_value=action(
            "SAVE_CHECKPOINT", None, coordinator.ACTION_FAILED
        ))
        actual = coordinator.DevelopmentGateCoordinator._for_test(
            {"SAVE_CHECKPOINT": adapter}
        ).coordinate(value())
        self.assertEqual(actual.status, "ACTION_FAILED_SAFE")
        adapter.assert_called_once()

    def test_exception_is_fail_safe_and_not_retried(self):
        adapter = mock.Mock(side_effect=RuntimeError)
        actual = coordinator.DevelopmentGateCoordinator._for_test(
            {"SAVE_CHECKPOINT": adapter}
        ).coordinate(value())
        self.assertEqual(actual.status, "ACTION_FAILED_SAFE")
        adapter.assert_called_once()

    def test_wrong_action_result_rejected(self):
        adapter = mock.Mock(return_value=action("RUN_TESTS", None))
        actual = coordinator.DevelopmentGateCoordinator._for_test(
            {"SAVE_CHECKPOINT": adapter}
        ).coordinate(value())
        self.assertEqual(actual.status, "ACTION_FAILED_SAFE")

    def test_approval_action_must_revalidate_to_ready(self):
        before = value(
            checkpoint_status="SAVED", checkpoint_ref=CHECKPOINT,
            test_tier="FULL", test_status="PASSED", commit_sha=SHA,
            pushed_sha=SHA, ci_status="SUCCESS", ci_head_sha=SHA,
            ci_run_id=1, approval_status="REQUIRED",
        )
        after = replace(before, approval_status="APPROVED")
        adapter = mock.Mock(return_value=action("REQUEST_APPROVAL", after))
        actual = coordinator.DevelopmentGateCoordinator._for_test(
            {"REQUEST_APPROVAL": adapter}
        ).coordinate(before)
        self.assertEqual((actual.status, actual.after_status),
                         ("ACTION_COMPLETED", "NEXT_GATE_READY"))

    def test_start_next_gate_requires_ready_evidence(self):
        ready = value(
            checkpoint_status="SAVED", checkpoint_ref=CHECKPOINT,
            test_tier="FULL", test_status="PASSED", commit_sha=SHA,
            pushed_sha=SHA, ci_status="SUCCESS", ci_head_sha=SHA,
            ci_run_id=1, approval_status="APPROVED",
        )
        adapter = mock.Mock(return_value=action("START_NEXT_GATE"))
        actual = coordinator.DevelopmentGateCoordinator._for_test(
            {"START_NEXT_GATE": adapter}
        ).coordinate(ready)
        self.assertEqual((actual.status, actual.next_gate_started),
                         ("NEXT_GATE_STARTED", True))
        adapter.assert_called_once()

    def test_no_builtin_production_activation_factory(self):
        self.assertFalse(hasattr(coordinator.DevelopmentGateCoordinator, "for_production"))
        self.assertFalse(hasattr(coordinator, "activate_production"))


if __name__ == "__main__":
    unittest.main()
