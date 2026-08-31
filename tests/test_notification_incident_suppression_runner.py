import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import notification_ledger as ledger  # noqa: E402
import notification_ledger_record_v02 as codec  # noqa: E402
import scheduled_runtime_runner as runner  # noqa: E402
import unattended_runtime as runtime  # noqa: E402
from tests.test_notification_ledger import event  # noqa: E402


EVENT_A = "a" * 64


def approval(occurred_at):
    value = event()
    value.update(
        event_type="JOB_WAITING_APPROVAL", severity="WARN",
        state="WAITING_APPROVAL", approval_required=True,
        occurred_at=occurred_at,
    )
    return value


class NotificationIncidentSuppressionRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="incident-suppression-runner-"
        )
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "ledger.json"
        self.lock = Path(self.temporary.name) / "runner.lock"
        self.store = ledger.NotificationLedger(self.path)
        self.loader = mock.Mock(return_value=("fixture-user", "fixture-app"))
        self.transport = mock.Mock(return_value={"status": 1})

    def execute(self, value, *, store=None, mode="MOCK_RUNTIME",
                live_notification_confirmed=False):
        return runner.run_once(
            value, mode=mode, ledger=self.store if store is None else store,
            live_notification_confirmed=live_notification_confirmed,
            credential_loader=self.loader, transport=self.transport,
            lock_path=self.lock,
        )

    def seed(self, value, recorded_at):
        record = codec.build_record(
            event_identity=EVENT_A,
            incident_identity=runtime.incident_identity(value),
            event_type=value["event_type"], recorded_at_utc=recorded_at,
        )
        self.assertIsNotNone(record)
        self.path.write_text(
            json.dumps([record], sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        return record

    def test_restart_equivalent_suppresses_same_completion_incident(self):
        first = event()
        first["occurred_at"] = "2026-09-01T00:00:00+00:00"
        second = dict(first, occurred_at="2026-09-01T00:01:00+00:00")
        self.assertEqual(self.execute(first).runtime_status,
                         "NOTIFICATION_DELIVERED")
        restarted = ledger.NotificationLedger(self.path)
        result = self.execute(second, store=restarted)
        self.assertEqual(result.runtime_status,
                         "NOTIFICATION_DUPLICATE_SUPPRESSED")
        self.assertEqual(result.runner_status, "COMPLETED")
        self.assertEqual(result.exit_code, 0)
        self.assertFalse(result.notification_attempted)
        self.assertEqual(self.transport.call_count, 1)

    def test_approval_inside_window_is_suppressed_before_transport(self):
        value = approval("2026-08-31T00:10:00+00:00")
        before = self.seed(value, "2026-08-31T00:00:00Z")
        result = self.execute(value)
        self.assertEqual(result.runtime_status,
                         "NOTIFICATION_DUPLICATE_SUPPRESSED")
        self.transport.assert_not_called()
        self.assertEqual(self.store._read(), [before])

    def test_approval_reminder_at_boundary_is_delivered_and_recorded(self):
        value = approval("2026-08-31T00:30:00+00:00")
        previous = self.seed(value, "2026-08-31T00:00:00Z")
        result = self.execute(value)
        self.assertEqual(result.runtime_status, "NOTIFICATION_DELIVERED")
        self.assertTrue(result.notification_attempted)
        self.transport.assert_called_once()
        rows = self.store._read()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["incident_identity"],
                         previous["incident_identity"])

    def test_live_runner_does_not_apply_incident_suppression(self):
        value = event()
        value["occurred_at"] = "2026-08-31T00:10:00+00:00"
        self.seed(value, "2026-08-31T00:00:00Z")
        result = self.execute(
            value, mode="LIVE_NOTIFICATION", live_notification_confirmed=True,
        )
        self.assertEqual(result.runtime_status, "NOTIFICATION_DELIVERED")
        self.transport.assert_called_once()
        self.assertEqual([row["ledger_version"] for row in self.store._read()],
                         ["0.2", "0.1"])

    def test_suppressed_cycle_releases_runner_lock(self):
        value = event()
        value["occurred_at"] = "2026-08-31T00:10:00+00:00"
        self.seed(value, "2026-08-31T00:00:00Z")
        result = self.execute(value)
        self.assertEqual(result.lock_status, "RELEASED")
        self.assertFalse(self.lock.exists())


if __name__ == "__main__":
    unittest.main()
