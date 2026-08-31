from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import notification_noise_control as policy  # noqa: E402


KEY = "a" * 64
OTHER_KEY = "b" * 64
NOW = "2026-08-31T13:00:00+09:00"


def evidence(event_type="JOB_WAITING_APPROVAL", **changes):
    base = policy.NotificationNoiseEvidence(event_type, KEY, NOW)
    return replace(base, **changes)


class NotificationNoiseControlTests(unittest.TestCase):
    def test_first_immediate_events_are_never_suppressed(self):
        for event_type in (
            "JOB_WAITING_APPROVAL", "JOB_FAILED_SAFE", "QUEUE_BLOCKED"
        ):
            with self.subTest(event_type=event_type):
                result = policy.evaluate(evidence(event_type))
                self.assertEqual(result.action, "DELIVER_IMMEDIATE")
                self.assertTrue(result.delivery_allowed)

    def test_first_completion_remains_normal(self):
        result = policy.evaluate(evidence("JOB_COMPLETED"))
        self.assertEqual(result.action, "DELIVER_NORMAL")
        self.assertTrue(result.delivery_allowed)

    def test_distinct_event_is_not_suppressed(self):
        result = policy.evaluate(evidence(
            last_delivered_event_key=OTHER_KEY,
            last_delivered_at="2026-08-31T12:59:59+09:00",
        ))
        self.assertEqual(result.status, "DELIVERY_SELECTED")

    def test_approval_duplicate_suppressed_before_30_minutes(self):
        result = policy.evaluate(evidence(
            last_delivered_event_key=KEY,
            last_delivered_at="2026-08-31T12:30:01+09:00",
        ))
        self.assertEqual((result.action, result.delivery_allowed),
                         ("SUPPRESS", False))

    def test_approval_reminder_selected_at_30_minutes(self):
        result = policy.evaluate(evidence(
            last_delivered_event_key=KEY,
            last_delivered_at="2026-08-31T12:30:00+09:00",
        ))
        self.assertEqual((result.status, result.reminder),
                         ("REMINDER_SELECTED", True))

    def test_failure_and_blocked_use_one_hour_window(self):
        for event_type in ("JOB_FAILED_SAFE", "QUEUE_BLOCKED"):
            with self.subTest(event_type=event_type):
                before = policy.evaluate(evidence(
                    event_type, last_delivered_event_key=KEY,
                    last_delivered_at="2026-08-31T12:00:01+09:00",
                ))
                boundary = policy.evaluate(evidence(
                    event_type, last_delivered_event_key=KEY,
                    last_delivered_at="2026-08-31T12:00:00+09:00",
                ))
                self.assertEqual(before.action, "SUPPRESS")
                self.assertTrue(boundary.reminder)

    def test_completion_duplicate_remains_suppressed_after_time(self):
        result = policy.evaluate(evidence(
            "JOB_COMPLETED", last_delivered_event_key=KEY,
            last_delivered_at="2026-08-01T12:00:00+09:00",
        ))
        self.assertEqual(result.status, "DUPLICATE_SUPPRESSED")

    def test_critical_boundary_never_downgraded_or_rerouted(self):
        result = policy.evaluate(evidence(
            "CRITICAL_STOP", last_delivered_event_key=KEY,
            last_delivered_at="2026-08-31T12:59:59+09:00",
        ))
        self.assertEqual(result.action, "PRESERVE_CRITICAL")
        self.assertFalse(result.delivery_allowed)
        self.assertIn("CRITICAL_SEND_POLICY_UNCHANGED", result.reason_codes)

    def test_invalid_and_contradictory_input_fails_closed(self):
        cases = (
            {},
            evidence("JOB_STARTED"),
            evidence(event_key="a" * 63),
            evidence(occurred_at="2026-08-31T13:00:00"),
            evidence(last_delivered_event_key=KEY),
            evidence(last_delivered_at=NOW),
            evidence(last_delivered_event_key=KEY,
                     last_delivered_at="2026-08-31T13:00:01+09:00"),
        )
        for value in cases:
            with self.subTest(value=value):
                result = policy.evaluate(value)
                self.assertEqual((result.status, result.action,
                                  result.delivery_allowed),
                                 ("INVALID_INPUT", "NONE", False))

    def test_policy_performs_no_io(self):
        with (mock.patch("builtins.open", side_effect=AssertionError),
              mock.patch("pathlib.Path.write_text", side_effect=AssertionError)):
            self.assertTrue(policy.evaluate(evidence()).delivery_allowed)


if __name__ == "__main__":
    unittest.main()
