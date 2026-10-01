from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_revalidation_cadence_guard as subject  # noqa: E402


def event(hour: int, minute: int = 17, reason: str = subject.UPSTREAM_REASON):
    outcome = "UNCONFIRMED" if reason == subject.UPSTREAM_REASON else "VALID"
    enabled = 0 if outcome == "UNCONFIRMED" else 1
    return subject.RevalidationEvent(
        datetime(2026, 10, 1, hour, minute, tzinfo=timezone.utc),
        outcome,
        enabled,
        reason,
    )


class RevalidationCadenceGuardTests(unittest.TestCase):
    def test_three_hourly_upstream_failure_groups_block(self):
        result = subject.assess((event(0), event(1), event(2)))
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertFalse(result.additional_live_batch_allowed)
        self.assertEqual(result.hourly_sequence_count, 1)
        self.assertEqual(
            result.reason_codes,
            ("UNEXPECTED_RECURRING_UPSTREAM_FAILURE_CADENCE",),
        )

    def test_valid_manual_batches_do_not_trigger_guard(self):
        result = subject.assess(
            (event(0, 40, "OFFICIAL_API_EXACT_MATCH"),
             event(2, 40, "OFFICIAL_API_EXACT_MATCH"))
        )
        self.assertEqual(result.status, subject.PASS)
        self.assertTrue(result.additional_live_batch_allowed)

    def test_two_failure_groups_are_not_called_a_recurring_cadence(self):
        result = subject.assess((event(0), event(1)))
        self.assertEqual(result.status, subject.PASS)

    def test_invalid_evidence_fails_closed(self):
        self.assertEqual(subject.assess([]).status, subject.FAIL_CLOSED)
        self.assertFalse(subject.assess(None).additional_live_batch_allowed)

    def test_parser_rejects_malformed_target_rows(self):
        with self.assertRaises(ValueError):
            subject.parse_export(
                ['INSERT INTO "affiliate_lifecycle_revalidation_event" broken;\n']
            )

    def test_cli_current_private_export_blocks_without_leaking_ids(self):
        completed = subprocess.run(
            [sys.executable, "-B", str(ROOT / "scripts" /
             "revenue_mvp_revalidation_cadence_guard.py")],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn('"status": "BLOCKED"', completed.stdout)
        self.assertNotIn("itm_", completed.stdout)
        self.assertNotIn("https://", completed.stdout)

    def test_cli_missing_export_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [sys.executable, "-B", str(ROOT / "scripts" /
                 "revenue_mvp_revalidation_cadence_guard.py"),
                 str(Path(directory) / "missing.sql")],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(completed.returncode, 2)
        self.assertIn('"status": "FAIL_CLOSED"', completed.stdout)


if __name__ == "__main__":
    unittest.main()
