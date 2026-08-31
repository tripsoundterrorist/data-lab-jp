from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import development_gate_evidence as gate_core  # noqa: E402
import development_next_gate_usage_permit as contract  # noqa: E402
import development_usage_protection_permit as usage_core  # noqa: E402


CHECKPOINT = "a" * 64
SHA = "b" * 40


def ready_gate():
    return gate_core.DevelopmentGateEvidence(
        "current-gate", "next-gate", checkpoint_status="SAVED",
        checkpoint_ref=CHECKPOINT, test_tier="REGRESSION",
        test_status="PASSED", commit_sha=SHA, pushed_sha=SHA,
        ci_status="SUCCESS", ci_head_sha=SHA, ci_run_id=43,
        approval_status="APPROVED",
    )


def usage(five=26, weekly=75, size="SMALL", reserve=True):
    return usage_core.UsageProtectionEvidence(
        five, weekly, size, reserve
    )


class DevelopmentNextGateUsagePermitTests(unittest.TestCase):
    def test_ready_small_gate_with_capacity_is_permitted(self):
        result = contract.evaluate(ready_gate(), usage())
        self.assertEqual(result.status, "NEXT_GATE_PERMITTED")
        self.assertTrue(result.next_gate_allowed)
        self.assertFalse(result.checkpoint_required)

    def test_incomplete_development_gate_blocks_before_usage_evaluation(self):
        incomplete = gate_core.DevelopmentGateEvidence(
            "current-gate", "next-gate"
        )
        with mock.patch.object(
            contract.usage_core, "evaluate", side_effect=AssertionError
        ):
            result = contract.evaluate(incomplete, usage())
        self.assertEqual(result.status, "NEXT_GATE_NOT_READY")
        self.assertFalse(result.next_gate_allowed)

    def test_rejected_development_evidence_retains_core_reason(self):
        result = contract.evaluate({}, usage())
        self.assertEqual(result.status, "DEVELOPMENT_EVIDENCE_REJECTED")
        self.assertIn("EVIDENCE_TYPE_INVALID", result.reason_codes)

    def test_unknown_usage_fails_closed_and_requires_checkpoint(self):
        result = contract.evaluate(ready_gate(), usage(five=None))
        self.assertEqual(result.status, "USAGE_PROTECTION_BLOCKED")
        self.assertFalse(result.next_gate_allowed)
        self.assertTrue(result.checkpoint_required)
        self.assertIn("USAGE_REMAINING_UNKNOWN", result.reason_codes)

    def test_five_hour_stop_requires_checkpoint(self):
        result = contract.evaluate(ready_gate(), usage(five=10))
        self.assertTrue(result.checkpoint_required)
        self.assertIn("FIVE_HOUR_STOP_THRESHOLD", result.reason_codes)

    def test_weekly_stop_requires_checkpoint(self):
        result = contract.evaluate(ready_gate(), usage(weekly=15))
        self.assertTrue(result.checkpoint_required)
        self.assertIn("WEEKLY_STOP_THRESHOLD", result.reason_codes)

    def test_large_task_buffer_blocks_without_forcing_checkpoint(self):
        for item, reason in (
            (usage(five=15, size="LARGE"), "FIVE_HOUR_LARGE_TASK_STOP"),
            (usage(weekly=20, size="LARGE"), "WEEKLY_LARGE_TASK_STOP"),
        ):
            with self.subTest(reason=reason):
                result = contract.evaluate(ready_gate(), item)
                self.assertFalse(result.next_gate_allowed)
                self.assertFalse(result.checkpoint_required)
                self.assertIn(reason, result.reason_codes)

    def test_operational_reserve_is_required(self):
        result = contract.evaluate(ready_gate(), usage(reserve=False))
        self.assertFalse(result.next_gate_allowed)
        self.assertTrue(result.checkpoint_required)
        self.assertIn(
            "OPERATIONAL_RESERVE_NOT_PROTECTED", result.reason_codes
        )

    def test_evaluator_performs_no_io(self):
        with (mock.patch("builtins.open", side_effect=AssertionError),
              mock.patch("pathlib.Path.write_text", side_effect=AssertionError)):
            result = contract.evaluate(ready_gate(), usage())
        self.assertTrue(result.next_gate_allowed)


if __name__ == "__main__":
    unittest.main()
