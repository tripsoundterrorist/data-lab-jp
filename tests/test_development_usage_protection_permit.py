from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import development_usage_protection_permit as permit  # noqa: E402


def evidence(five=41, weekly=78, size="SMALL", reserve=True):
    return permit.UsageProtectionEvidence(five, weekly, size, reserve)


class DevelopmentUsageProtectionPermitTests(unittest.TestCase):
    def test_current_small_gate_is_permitted(self):
        result = permit.evaluate(evidence())
        self.assertEqual(result.status, "PERMITTED")
        self.assertTrue(result.new_task_allowed)
        self.assertFalse(result.checkpoint_required)

    def test_unknown_remaining_fails_closed_and_requires_checkpoint(self):
        for value in (evidence(five=None), evidence(weekly=None)):
            with self.subTest(value=value):
                result = permit.evaluate(value)
                self.assertEqual(result.status, "BLOCKED")
                self.assertFalse(result.new_task_allowed)
                self.assertTrue(result.checkpoint_required)

    def test_five_hour_stop_boundary_is_inclusive(self):
        result = permit.evaluate(evidence(five=10))
        self.assertEqual(result.status, "CHECKPOINT_AND_STOP")
        self.assertTrue(result.checkpoint_required)
        self.assertIn("FIVE_HOUR_STOP_THRESHOLD", result.reason_codes)

    def test_weekly_stop_boundary_is_inclusive(self):
        result = permit.evaluate(evidence(weekly=15))
        self.assertEqual(result.status, "CHECKPOINT_AND_STOP")
        self.assertIn("WEEKLY_STOP_THRESHOLD", result.reason_codes)

    def test_stricter_stop_reasons_are_both_retained(self):
        result = permit.evaluate(evidence(five=10, weekly=15))
        self.assertEqual(
            result.reason_codes,
            ("FIVE_HOUR_STOP_THRESHOLD", "WEEKLY_STOP_THRESHOLD"),
        )

    def test_large_task_five_hour_boundary_is_blocked(self):
        result = permit.evaluate(evidence(five=15, size="LARGE"))
        self.assertEqual(result.status, "LARGE_TASK_BLOCKED")
        self.assertFalse(result.checkpoint_required)
        self.assertIn("FIVE_HOUR_LARGE_TASK_STOP", result.reason_codes)

    def test_large_task_weekly_boundary_is_blocked(self):
        result = permit.evaluate(evidence(weekly=20, size="LARGE"))
        self.assertEqual(result.status, "LARGE_TASK_BLOCKED")
        self.assertIn("WEEKLY_LARGE_TASK_STOP", result.reason_codes)

    def test_small_task_can_use_protected_buffer_above_stop_thresholds(self):
        result = permit.evaluate(evidence(five=11, weekly=16))
        self.assertEqual(result.status, "PERMITTED")
        self.assertTrue(result.new_task_allowed)

    def test_operational_reserve_is_mandatory(self):
        result = permit.evaluate(evidence(reserve=False))
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(result.checkpoint_required)
        self.assertIn("OPERATIONAL_RESERVE_NOT_PROTECTED", result.reason_codes)

    def test_invalid_types_and_ranges_fail_closed(self):
        cases = (
            {}, evidence(five=True), evidence(weekly=101),
            evidence(size="MEDIUM"),
            permit.UsageProtectionEvidence(50, 50, "SMALL", 1),
        )
        for value in cases:
            with self.subTest(value=value):
                self.assertFalse(permit.evaluate(value).new_task_allowed)

    def test_evaluator_performs_no_io(self):
        with (mock.patch("builtins.open", side_effect=AssertionError),
              mock.patch("pathlib.Path.write_text", side_effect=AssertionError)):
            self.assertTrue(permit.evaluate(evidence()).new_task_allowed)


if __name__ == "__main__":
    unittest.main()
