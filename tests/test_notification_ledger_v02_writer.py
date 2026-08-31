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
import unattended_runtime as runtime  # noqa: E402
from tests.test_notification_ledger import event  # noqa: E402


EVENT_A = "a" * 64
EVENT_B = "b" * 64
INCIDENT = "c" * 64


def v01(identity=EVENT_A):
    return {
        "ledger_version": "0.1", "event_identity": identity,
        "event_type": "JOB_COMPLETED",
        "delivery_status": "NOTIFICATION_DELIVERED",
        "recorded_at_utc": "2026-08-31T05:00:00Z",
    }


class NotificationLedgerV02WriterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ledger-v02-writer-")
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "ledger.json"
        self.store = ledger.NotificationLedger(self.path)

    def write(self, rows):
        self.path.write_text(
            json.dumps(rows, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )

    def rows(self):
        return self.store._read()

    def test_explicit_writer_appends_exact_v02_record(self):
        with self.store.transaction(writable=True) as transaction:
            status = transaction.record_success_v02(
                EVENT_A, INCIDENT, "JOB_WAITING_APPROVAL"
            )
        self.assertEqual(status, "RECORDED")
        self.assertEqual(codec.validate_record(self.rows()[0]), "0.2")
        self.assertEqual(self.rows()[0]["incident_identity"], INCIDENT)

    def test_mixed_append_preserves_existing_v01(self):
        original = v01()
        self.write([original])
        with self.store.transaction(writable=True) as transaction:
            transaction.record_success_v02(
                EVENT_B, INCIDENT, "JOB_WAITING_APPROVAL"
            )
        rows = self.rows()
        self.assertEqual(rows[0], original)
        self.assertEqual([row["ledger_version"] for row in rows], ["0.1", "0.2"])

    def test_duplicate_v02_is_idempotent(self):
        with self.store.transaction(writable=True) as transaction:
            transaction.record_success_v02(
                EVENT_A, INCIDENT, "JOB_WAITING_APPROVAL"
            )
        before = self.path.read_bytes()
        with mock.patch.object(self.store, "_replace", side_effect=AssertionError):
            with self.store.transaction(writable=True) as transaction:
                status = transaction.record_success_v02(
                    EVENT_A, INCIDENT, "JOB_WAITING_APPROVAL"
                )
        self.assertEqual(status, "NO_CHANGE")
        self.assertEqual(self.path.read_bytes(), before)

    def test_existing_v01_identity_is_not_upgraded(self):
        self.write([v01()])
        before = self.path.read_bytes()
        with self.store.transaction(writable=True) as transaction:
            status = transaction.record_success_v02(
                EVENT_A, INCIDENT, "JOB_WAITING_APPROVAL"
            )
        self.assertEqual(status, "NO_CHANGE")
        self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_incident_fails_before_replace(self):
        with mock.patch.object(self.store, "_replace", side_effect=AssertionError):
            with self.store.transaction(writable=True) as transaction:
                with self.assertRaisesRegex(ledger.LedgerError,
                                             "LEDGER_RECORD_INVALID"):
                    transaction.record_success_v02(
                        EVENT_A, "c" * 63, "JOB_WAITING_APPROVAL"
                    )
        self.assertFalse(self.path.exists())

    def test_read_only_transaction_cannot_write_v02(self):
        with self.store.transaction() as transaction:
            with self.assertRaisesRegex(ledger.LedgerError, "LEDGER_READ_ONLY"):
                transaction.record_success_v02(
                    EVENT_A, INCIDENT, "JOB_WAITING_APPROVAL"
                )

    def test_replace_failure_keeps_existing_snapshot(self):
        self.write([v01()])
        before = self.path.read_bytes()
        with mock.patch.object(ledger.os, "replace", side_effect=OSError):
            with self.assertRaisesRegex(ledger.LedgerError,
                                         "LEDGER_WRITE_FAILED"):
                with self.store.transaction(writable=True) as transaction:
                    transaction.record_success_v02(
                        EVENT_B, INCIDENT, "JOB_WAITING_APPROVAL"
                    )
        self.assertEqual(self.path.read_bytes(), before)

    def test_recorded_timestamp_is_utc(self):
        with self.store.transaction(writable=True) as transaction:
            transaction.record_success_v02(
                EVENT_A, INCIDENT, "JOB_WAITING_APPROVAL"
            )
        self.assertTrue(self.rows()[0]["recorded_at_utc"].endswith("Z"))

    def test_runtime_does_not_call_v02_writer(self):
        loader = mock.Mock(return_value=("fixture-user", "fixture-app"))
        transport = mock.Mock(return_value={"status": 1})
        with mock.patch.object(
            ledger.LedgerTransaction, "record_success_v02",
            side_effect=AssertionError,
        ) as writer:
            result = runtime.process_notification(
                event(), mode="MOCK_RUNTIME", ledger=self.store,
                credential_loader=loader, transport=transport,
            )
        self.assertTrue(result.delivery_succeeded)
        writer.assert_not_called()
        self.assertEqual(self.rows()[0]["ledger_version"], "0.1")


if __name__ == "__main__":
    unittest.main()
