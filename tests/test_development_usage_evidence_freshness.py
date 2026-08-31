from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import development_usage_evidence_freshness as freshness  # noqa: E402
import development_usage_protection_permit as usage_core  # noqa: E402


NOW = 2_000_000_000


def snapshot(**changes):
    values = {
        "snapshot_version": freshness.SNAPSHOT_VERSION,
        "source": freshness.TRUSTED_SOURCE,
        "observed_at_epoch_s": NOW,
        "five_hour_remaining_pct": 86,
        "weekly_remaining_pct": 74,
        "task_size": "SMALL",
        "operational_reserve_protected": True,
    }
    values.update(changes)
    return freshness.UsageEvidenceSnapshot(**values)


class DevelopmentUsageEvidenceFreshnessTests(unittest.TestCase):
    def test_current_user_confirmed_snapshot_is_fresh(self):
        result = freshness.evaluate(snapshot(), evaluated_at_epoch_s=NOW)
        self.assertEqual(result.status, "SNAPSHOT_FRESH")
        self.assertEqual(result.contract_version, freshness.CONTRACT_VERSION)
        self.assertEqual(
            result.evidence,
            usage_core.UsageProtectionEvidence(86, 74, "SMALL", True),
        )
        self.assertFalse(result.checkpoint_required)

    def test_exact_maximum_age_is_accepted(self):
        result = freshness.evaluate(
            snapshot(observed_at_epoch_s=NOW - freshness.MAX_AGE_SECONDS),
            evaluated_at_epoch_s=NOW,
        )
        self.assertEqual(result.status, "SNAPSHOT_FRESH")

    def test_one_second_over_maximum_age_fails_closed(self):
        result = freshness.evaluate(
            snapshot(observed_at_epoch_s=NOW - freshness.MAX_AGE_SECONDS - 1),
            evaluated_at_epoch_s=NOW,
        )
        self.assertEqual(result.status, "SNAPSHOT_STALE")
        self.assertIsNone(result.evidence)
        self.assertTrue(result.checkpoint_required)

    def test_future_snapshot_is_rejected(self):
        result = freshness.evaluate(
            snapshot(observed_at_epoch_s=NOW + 1),
            evaluated_at_epoch_s=NOW,
        )
        self.assertIn("USAGE_SNAPSHOT_FROM_FUTURE", result.reason_codes)
        self.assertTrue(result.checkpoint_required)

    def test_identity_is_exact_and_fail_closed(self):
        for item in (
            snapshot(snapshot_version="9.9"),
            snapshot(source="SCREENSHOT_INFERRED"),
            {},
        ):
            with self.subTest(item=item):
                result = freshness.evaluate(item, evaluated_at_epoch_s=NOW)
                self.assertEqual(result.status, "SNAPSHOT_REJECTED")
                self.assertIsNone(result.evidence)

    def test_timestamp_types_and_ranges_are_strict(self):
        cases = (
            (snapshot(observed_at_epoch_s=True), NOW),
            (snapshot(observed_at_epoch_s=-1), NOW),
            (snapshot(), True),
            (snapshot(), -1),
        )
        for item, evaluated in cases:
            with self.subTest(item=item, evaluated=evaluated):
                result = freshness.evaluate(
                    item, evaluated_at_epoch_s=evaluated
                )
                self.assertIn(
                    "USAGE_SNAPSHOT_TIMESTAMP_INVALID", result.reason_codes
                )

    def test_payload_is_passed_through_for_usage_core_to_classify(self):
        result = freshness.evaluate(
            snapshot(five_hour_remaining_pct=None, task_size="LARGE"),
            evaluated_at_epoch_s=NOW,
        )
        self.assertEqual(result.status, "SNAPSHOT_FRESH")
        permit = usage_core.evaluate(result.evidence)
        self.assertFalse(permit.new_task_allowed)
        self.assertIn("USAGE_REMAINING_UNKNOWN", permit.reason_codes)

    def test_evaluator_reads_no_clock_or_io(self):
        with (mock.patch("time.time", side_effect=AssertionError),
              mock.patch("builtins.open", side_effect=AssertionError),
              mock.patch("pathlib.Path.write_text", side_effect=AssertionError)):
            result = freshness.evaluate(snapshot(), evaluated_at_epoch_s=NOW)
        self.assertEqual(result.status, "SNAPSHOT_FRESH")


if __name__ == "__main__":
    unittest.main()
