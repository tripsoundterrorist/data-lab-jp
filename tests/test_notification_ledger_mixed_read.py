import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ledger_recovery as recovery  # noqa: E402
import notification_ledger as ledger  # noqa: E402
import notification_ledger_record_v02 as codec  # noqa: E402


EVENT_A = "a" * 64
EVENT_B = "b" * 64
EVENT_C = "c" * 64
INCIDENT = "d" * 64


def v01(identity=EVENT_A):
    return {
        "ledger_version": "0.1", "event_identity": identity,
        "event_type": "JOB_COMPLETED",
        "delivery_status": "NOTIFICATION_DELIVERED",
        "recorded_at_utc": "2026-08-31T05:00:00Z",
    }


def v02(identity=EVENT_B):
    record = codec.build_record(
        event_identity=identity, incident_identity=INCIDENT,
        event_type="JOB_WAITING_APPROVAL",
        recorded_at_utc="2026-08-31T05:30:00Z",
    )
    assert record is not None
    return record


class NotificationLedgerMixedReadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ledger-mixed-read-")
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "ledger.json"
        self.store = ledger.NotificationLedger(self.path)

    def write(self, rows):
        self.path.write_text(
            json.dumps(rows, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )

    def test_reader_returns_mixed_records_unchanged(self):
        rows = [v01(), v02()]
        self.write(rows)
        self.assertEqual(self.store._read(), rows)

    def test_lookup_uses_exact_identity_across_versions(self):
        self.write([v01(), v02()])
        with self.store.transaction() as transaction:
            self.assertEqual(transaction.lookup(EVENT_A), "DELIVERED")
            self.assertEqual(transaction.lookup(EVENT_B), "DELIVERED")
            self.assertEqual(transaction.lookup(EVENT_C), "NEW")

    def test_recovery_reports_mixed_snapshot_healthy(self):
        self.write([v01(), v02()])
        result = recovery.inspect_ledger(self.store)
        self.assertEqual(result.recovery_status, recovery.HEALTHY)
        self.assertEqual(result.ledger_version_detected, "MIXED_0.1_0.2")
        self.assertEqual(result.record_count, 2)

    def test_recovery_reports_v02_only_healthy(self):
        self.write([v02()])
        result = recovery.inspect_ledger(self.store)
        self.assertEqual(result.recovery_status, recovery.HEALTHY)
        self.assertEqual(result.ledger_version_detected, "0.2")

    def test_existing_writer_still_appends_v01_only(self):
        self.write([v02()])
        with self.store.transaction(writable=True) as transaction:
            transaction.record_success(EVENT_C, "JOB_COMPLETED")
        rows = self.store._read()
        self.assertEqual([row["ledger_version"] for row in rows], ["0.2", "0.1"])
        self.assertNotIn("incident_identity", rows[1])

    def test_existing_v01_record_is_not_rewritten(self):
        original = v01()
        self.write([original, v02()])
        with self.store.transaction(writable=True) as transaction:
            transaction.record_success(EVENT_C, "JOB_COMPLETED")
        self.assertEqual(self.store._read()[0], original)

    def test_invalid_v02_incident_blocks_reader_and_recovery(self):
        invalid = v02()
        invalid["incident_identity"] = "d" * 63
        self.write([v01(), invalid])
        with self.assertRaisesRegex(ledger.LedgerError, "LEDGER_CORRUPT"):
            self.store._read()
        result = recovery.inspect_ledger(self.store)
        self.assertEqual(result.recovery_status,
                         recovery.MANUAL_REVIEW_REQUIRED)
        self.assertIn("LEDGER_CORRUPT", result.reason_codes)

    def test_duplicate_exact_identity_across_versions_blocks(self):
        self.write([v01(), v02(EVENT_A)])
        with self.assertRaisesRegex(ledger.LedgerError, "LEDGER_CORRUPT"):
            self.store._read()
        self.assertIn("LEDGER_CORRUPT",
                      recovery.inspect_ledger(self.store).reason_codes)

    def test_unknown_version_remains_unsupported_and_corrupt(self):
        unknown = v01()
        unknown["ledger_version"] = "9"
        self.write([unknown])
        result = recovery.inspect_ledger(self.store)
        self.assertEqual(result.ledger_version_detected, "UNSUPPORTED")
        self.assertIn("LEDGER_CORRUPT", result.reason_codes)


if __name__ == "__main__":
    unittest.main()
