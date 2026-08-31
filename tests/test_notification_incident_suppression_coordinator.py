from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import notification_incident_suppression_coordinator as coordinator  # noqa: E402
import notification_ledger_record_v02 as codec  # noqa: E402


INCIDENT = "a" * 64
EVENT_A = "b" * 64
EVENT_B = "c" * 64
NOW = "2026-08-31T13:00:00+00:00"


def v01():
    return {
        "ledger_version": "0.1", "event_identity": EVENT_A,
        "event_type": "JOB_WAITING_APPROVAL",
        "delivery_status": "NOTIFICATION_DELIVERED",
        "recorded_at_utc": "2026-08-31T12:50:00Z",
    }


def v02(*, event_type="JOB_WAITING_APPROVAL",
        recorded_at="2026-08-31T12:50:00Z"):
    record = codec.build_record(
        event_identity=EVENT_B, incident_identity=INCIDENT,
        event_type=event_type, recorded_at_utc=recorded_at,
    )
    assert record is not None
    return record


def decide(records, event_type="JOB_WAITING_APPROVAL", occurred_at=NOW,
           incident_identity=INCIDENT):
    return coordinator.coordinate(
        records=records, event_type=event_type,
        incident_identity=incident_identity, occurred_at=occurred_at,
    )


class NotificationIncidentSuppressionCoordinatorTests(unittest.TestCase):
    def test_empty_snapshot_selects_first_delivery(self):
        result = decide([])
        self.assertEqual(result.status, "DELIVERY_SELECTED")
        self.assertTrue(result.delivery_allowed)
        self.assertEqual(result.evidence_status, "NO_V02_EVIDENCE")

    def test_v01_only_never_infers_incident_suppression(self):
        result = decide([v01()])
        self.assertTrue(result.delivery_allowed)
        self.assertEqual(result.evidence_status, "NO_V02_EVIDENCE")

    def test_v02_duplicate_is_suppressed_inside_window(self):
        result = decide([v02()])
        self.assertEqual((result.status, result.action),
                         ("DUPLICATE_SUPPRESSED", "SUPPRESS"))
        self.assertFalse(result.delivery_allowed)

    def test_v02_approval_reminder_selected_at_boundary(self):
        result = decide(
            [v02(recorded_at="2026-08-31T12:30:00Z")],
        )
        self.assertEqual(result.status, "REMINDER_SELECTED")
        self.assertTrue(result.delivery_allowed)
        self.assertTrue(result.reminder)

    def test_distinct_incident_selects_delivery(self):
        result = decide([v02()], incident_identity="d" * 64)
        self.assertEqual(result.status, "DELIVERY_SELECTED")
        self.assertTrue(result.delivery_allowed)

    def test_completion_duplicate_remains_suppressed(self):
        result = decide(
            [v02(event_type="JOB_COMPLETED",
                 recorded_at="2026-08-01T12:00:00Z")],
            event_type="JOB_COMPLETED",
        )
        self.assertEqual(result.status, "DUPLICATE_SUPPRESSED")

    def test_critical_boundary_is_preserved(self):
        result = decide([], event_type="CRITICAL_STOP")
        self.assertEqual(result.action, "PRESERVE_CRITICAL")
        self.assertFalse(result.delivery_allowed)

    def test_invalid_snapshot_and_identity_fail_closed(self):
        for records, identity in (({}, INCIDENT), ([{}], INCIDENT), ([], "x")):
            with self.subTest(records=records, identity=identity):
                result = decide(records, incident_identity=identity)
                self.assertEqual(result.status, "COORDINATION_BLOCKED")
                self.assertFalse(result.delivery_allowed)

    def test_invalid_policy_input_fails_closed(self):
        result = decide([], event_type="JOB_STARTED")
        self.assertEqual(result.status, "COORDINATION_BLOCKED")
        self.assertIn("EVENT_TYPE_INVALID", result.reason_codes)

    def test_inputs_are_not_mutated(self):
        records = [v01(), v02()]
        before = deepcopy(records)
        decide(records)
        self.assertEqual(records, before)

    def test_coordinator_performs_no_io(self):
        with (mock.patch("builtins.open", side_effect=AssertionError),
              mock.patch("pathlib.Path.write_text", side_effect=AssertionError)):
            self.assertTrue(decide([]).delivery_allowed)


if __name__ == "__main__":
    unittest.main()
