from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import development_gate_evidence as evidence  # noqa: E402


CHECKPOINT = "a" * 64
SHA = "b" * 40


def complete(**changes):
    base = evidence.DevelopmentGateEvidence(
        current_gate_id="tier-ci-v0.2",
        next_gate_id="gate-evidence-v0.1",
        checkpoint_status="SAVED",
        checkpoint_ref=CHECKPOINT,
        test_tier="FULL",
        test_status="PASSED",
        commit_sha=SHA,
        pushed_sha=SHA,
        ci_status="SUCCESS",
        ci_head_sha=SHA,
        ci_run_id=33349412215,
        approval_status="NOT_REQUIRED",
    )
    return replace(base, **changes)


class DevelopmentGateEvidenceTests(unittest.TestCase):
    def test_complete_evidence_allows_next_gate(self):
        result = evidence.evaluate(complete())
        self.assertEqual(result.status, "NEXT_GATE_READY")
        self.assertEqual(result.next_action, "START_NEXT_GATE")
        self.assertTrue(result.next_gate_allowed)

    def test_approved_boundary_allows_next_gate(self):
        self.assertTrue(evidence.evaluate(complete(approval_status="APPROVED")).next_gate_allowed)

    def test_missing_checkpoint_selects_checkpoint_only(self):
        result = evidence.evaluate(evidence.DevelopmentGateEvidence("gate-a", "gate-b"))
        self.assertEqual((result.status, result.next_action),
                         ("CHECKPOINT_REQUIRED", "SAVE_CHECKPOINT"))

    def test_missing_test_selects_tests_only(self):
        result = evidence.evaluate(complete(test_tier=None, test_status=None,
                                            commit_sha=None, pushed_sha=None,
                                            ci_status=None, ci_head_sha=None,
                                            ci_run_id=None, approval_status=None))
        self.assertEqual((result.status, result.next_action), ("TEST_REQUIRED", "RUN_TESTS"))

    def test_missing_commit_selects_commit_push_only(self):
        result = evidence.evaluate(complete(commit_sha=None, pushed_sha=None,
                                            ci_status=None, ci_head_sha=None,
                                            ci_run_id=None, approval_status=None))
        self.assertEqual((result.status, result.next_action),
                         ("COMMIT_PUSH_REQUIRED", "COMMIT_AND_PUSH"))

    def test_missing_ci_selects_wait_only(self):
        result = evidence.evaluate(complete(ci_status=None, ci_head_sha=None,
                                            ci_run_id=None, approval_status=None))
        self.assertEqual((result.status, result.next_action), ("CI_REQUIRED", "WAIT_FOR_CI"))

    def test_required_approval_never_auto_starts(self):
        result = evidence.evaluate(complete(approval_status="REQUIRED"))
        self.assertEqual((result.status, result.next_action, result.next_gate_allowed),
                         ("APPROVAL_REQUIRED", "REQUEST_APPROVAL", False))

    def test_fail_closed_cases(self):
        cases = (
            complete(current_gate_id="UPPER"),
            complete(next_gate_id="tier-ci-v0.2"),
            complete(checkpoint_status="RECOVERY_BLOCKED"),
            complete(checkpoint_ref="a" * 63),
            complete(test_tier="SMOKE"),
            complete(test_status="FAILED"),
            complete(commit_sha="b" * 39),
            complete(pushed_sha="c" * 40),
            complete(ci_status="QUEUED"),
            complete(ci_head_sha="c" * 40),
            complete(ci_run_id=True),
            complete(approval_status="UNKNOWN"),
            complete(approval_status="DENIED"),
        )
        for value in cases:
            with self.subTest(value=value):
                result = evidence.evaluate(value)
                self.assertEqual((result.status, result.next_action,
                                  result.next_gate_allowed),
                                 ("EVIDENCE_REJECTED", "NONE", False))

    def test_non_contract_input_rejected(self):
        self.assertEqual(evidence.evaluate({}).reason_codes, ("EVIDENCE_TYPE_INVALID",))

    def test_pure_decision_performs_no_io(self):
        with (mock.patch("builtins.open", side_effect=AssertionError),
              mock.patch("pathlib.Path.write_text", side_effect=AssertionError)):
            self.assertTrue(evidence.evaluate(complete()).next_gate_allowed)


if __name__ == "__main__":
    unittest.main()
