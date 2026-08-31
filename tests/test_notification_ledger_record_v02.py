from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import notification_ledger_record_v02 as codec  # noqa: E402


EVENT_A = "a" * 64
EVENT_B = "b" * 64
INCIDENT = "c" * 64


def v01(**changes):
    record = {
        "ledger_version": "0.1", "event_identity": EVENT_A,
        "event_type": "JOB_WAITING_APPROVAL",
        "delivery_status": "NOTIFICATION_DELIVERED",
        "recorded_at_utc": "2026-08-31T05:00:00Z",
    }
    record.update(changes)
    return record


def v02(**changes):
    record = codec.build_record(
        event_identity=EVENT_B, incident_identity=INCIDENT,
        event_type="JOB_WAITING_APPROVAL",
        recorded_at_utc="2026-08-31T05:30:00Z",
    )
    assert record is not None
    record.update(changes)
    return record


class NotificationLedgerRecordV02Tests(unittest.TestCase):
    def test_v01_and_v02_records_are_recognized(self):
        self.assertEqual(codec.validate_record(v01()), "0.1")
        self.assertEqual(codec.validate_record(v02()), "0.2")

    def test_builder_emits_exact_v02_schema(self):
        record = v02()
        self.assertEqual(set(record), codec.V02_FIELDS)
        self.assertEqual(record["ledger_version"], "0.2")

    def test_mixed_snapshot_is_backward_compatible(self):
        result = codec.validate_snapshot([v01(), v02()])
        self.assertEqual((result.status, result.v01_count, result.v02_count),
                         ("SNAPSHOT_VALID", 1, 1))

    def test_empty_and_v01_only_snapshots_are_valid(self):
        self.assertEqual(codec.validate_snapshot([]).status, "SNAPSHOT_VALID")
        self.assertEqual(codec.validate_snapshot([v01()]).status, "SNAPSHOT_VALID")

    def test_v01_does_not_infer_incident_evidence(self):
        result = codec.latest_incident_delivery([v01()], INCIDENT)
        self.assertEqual(result.status, "NO_V02_EVIDENCE")
        self.assertFalse(result.evidence_available)

    def test_latest_v02_delivery_is_selected(self):
        earlier = v02(event_identity=EVENT_A,
                      recorded_at_utc="2026-08-31T05:10:00Z")
        latest = v02(recorded_at_utc="2026-08-31T05:40:00Z")
        result = codec.latest_incident_delivery([latest, earlier], INCIDENT)
        self.assertEqual(result.recorded_at_utc, "2026-08-31T05:40:00Z")
        self.assertTrue(result.evidence_available)

    def test_other_incident_is_not_evidence(self):
        result = codec.latest_incident_delivery(
            [v02(incident_identity="d" * 64)], INCIDENT
        )
        self.assertEqual(result.status, "NO_V02_EVIDENCE")

    def test_duplicate_exact_event_identity_blocks_snapshot(self):
        result = codec.validate_snapshot([v01(), v02(event_identity=EVENT_A)])
        self.assertEqual(result.status, "SNAPSHOT_INVALID")
        self.assertIn("LEDGER_EVENT_IDENTITY_DUPLICATE", result.reason_codes)

    def test_invalid_records_fail_closed(self):
        cases = (
            {},
            v01(extra=True),
            v01(ledger_version="9"),
            v01(event_identity="a" * 63),
            v01(delivery_status="FAILED"),
            v01(recorded_at_utc="2026-08-31T05:00:00+09:00"),
            v02(incident_identity="c" * 63),
        )
        for record in cases:
            with self.subTest(record=record):
                self.assertIsNone(codec.validate_record(record))
                self.assertEqual(codec.validate_snapshot([record]).status,
                                 "SNAPSHOT_INVALID")

    def test_invalid_snapshot_or_lookup_identity_blocks(self):
        self.assertEqual(codec.latest_incident_delivery({}, INCIDENT).status,
                         "EVIDENCE_BLOCKED")
        self.assertEqual(codec.latest_incident_delivery([], "x").status,
                         "EVIDENCE_INVALID")

    def test_inputs_are_not_mutated(self):
        records = [v01(), v02()]
        before = deepcopy(records)
        codec.validate_snapshot(records)
        codec.latest_incident_delivery(records, INCIDENT)
        self.assertEqual(records, before)

    def test_codec_performs_no_io(self):
        with (mock.patch("builtins.open", side_effect=AssertionError),
              mock.patch("pathlib.Path.write_text", side_effect=AssertionError)):
            self.assertEqual(codec.validate_snapshot([v01(), v02()]).status,
                             "SNAPSHOT_VALID")


if __name__ == "__main__":
    unittest.main()
