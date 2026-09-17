from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


generator = load("saved_lifecycle_receipts", "generate-saved-lifecycle-receipts.py")
builder = load("saved_receipt_builder", "build-public-data.py")
NOW = datetime(2026, 9, 17, 0, 0, tzinfo=timezone.utc)
STAMP = "2026-09-16T07:00:42Z"


def create_database(path: Path, *, master_time=STAMP, snapshot_time=STAMP, second=False):
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE items (
          id INTEGER PRIMARY KEY, site TEXT, service TEXT, floor TEXT,
          content_id TEXT, last_observed_at TEXT
        );
        CREATE TABLE item_snapshots (
          id INTEGER PRIMARY KEY, item_id INTEGER, observed_at TEXT
        );
        """
    )
    connection.execute(
        "INSERT INTO items VALUES (1,'FANZA','digital','videoa','private-one',?)",
        (master_time,),
    )
    if snapshot_time is not None:
        connection.execute(
            "INSERT INTO item_snapshots VALUES (1,1,?)", (snapshot_time,)
        )
    if second:
        connection.execute(
            "INSERT INTO items VALUES (2,'FANZA','digital','videoa','private-two',?)",
            (master_time,),
        )
        connection.execute(
            "INSERT INTO item_snapshots VALUES (2,2,?)", (snapshot_time,)
        )
    connection.commit()
    connection.close()


class SavedLifecycleReceiptTests(unittest.TestCase):
    def generate(self, **kwargs):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        database = Path(temporary.name) / "saved.db"
        create_database(database, **kwargs)
        return generator.generate_receipts(database, as_of=NOW)

    def test_saved_row_generates_exactly_one_unknown_non_candidate_receipt(self):
        receipts = self.generate()
        self.assertEqual(len(receipts), 1)
        receipt = receipts[0]
        self.assertRegex(receipt.public_id, r"^itm_[0-9a-f]{24}$")
        self.assertIs(receipt.observation.observation, generator.Observation.UNKNOWN)
        self.assertIsNone(receipt.observation.expected_content_id_match)
        self.assertIsNone(receipt.observation.affiliate_link_observed)
        self.assertTrue(receipt.freshness_confirmed)
        self.assertEqual(
            receipt.observation.reason_codes,
            (
                "SAVED_AFFILIATE_EVIDENCE_UNAVAILABLE",
                "SAVED_COLLECTION_NOT_EXACT_ITEM_VERIFICATION",
            ),
        )
        master = {1: {"public_id": receipt.public_id}}
        confidence = {1: {"observation_stats": {"last_observed_at": STAMP}}}
        selected, excluded = builder.filter_master_items_by_lifecycle_receipts(
            master, confidence, receipts
        )
        self.assertEqual(selected, {})
        self.assertEqual(excluded, 1)

    def test_stale_or_future_is_not_fresh(self):
        for stamp in ("2026-09-15T00:00:00Z", "2026-09-17T00:00:01Z"):
            with self.subTest(stamp=stamp):
                receipt = self.generate(master_time=stamp, snapshot_time=stamp)[0]
                self.assertFalse(receipt.freshness_confirmed)
                self.assertIn(
                    "SAVED_OBSERVATION_STALE_OR_FUTURE",
                    receipt.observation.reason_codes,
                )

    def test_missing_saved_observation_yields_closed_receipt(self):
        receipt = self.generate(snapshot_time=None)[0]
        self.assertIsNone(receipt.observation.observed_at)
        self.assertFalse(receipt.freshness_confirmed)
        self.assertEqual(receipt.observation.reason_codes, ("SAVED_OBSERVATION_MISSING",))

    def test_item_timestamp_mismatch_fails_closed(self):
        with self.assertRaisesRegex(generator.SavedReceiptError, "ITEM_MISMATCH"):
            self.generate(master_time="2026-09-16T06:00:00Z")

    def test_duplicate_public_id_fails_closed(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        database = Path(temporary.name) / "saved.db"
        create_database(database, second=True)
        with mock.patch.object(generator, "public_item_id", return_value="itm_" + "0" * 24):
            with self.assertRaisesRegex(generator.SavedReceiptError, "DUPLICATE"):
                generator.generate_receipts(database, as_of=NOW)

    def test_packet_round_trip_is_builder_compatible_and_sanitized(self):
        receipts = self.generate()
        packet = generator.create_packet(receipts, as_of=NOW)
        generator.safety_scan(packet)
        restored = generator.validate_packet(json.loads(json.dumps(packet)))
        self.assertEqual(len(restored), 1)
        self.assertIs(type(restored[0]), builder.LifecycleReceipt)
        text = json.dumps(packet, sort_keys=True).casefold()
        for forbidden in (
            "private-one", "affiliate_url", "affiliateurl", "api_id",
            "affiliate_id", "raw_response", "credential", "item_url",
            "source_offset", "source_position",
        ):
            self.assertNotIn(forbidden, text)

    def test_packet_duplicate_and_freshness_tamper_fail_closed(self):
        packet = generator.create_packet(self.generate(), as_of=NOW)
        packet["receipts"].append(dict(packet["receipts"][0]))
        with self.assertRaisesRegex(generator.SavedReceiptError, "DUPLICATE"):
            generator.validate_packet(packet)
        packet = generator.create_packet(self.generate(), as_of=NOW)
        packet["receipts"][0]["freshness_confirmed"] = False
        with self.assertRaisesRegex(generator.SavedReceiptError, "FRESHNESS_MISMATCH"):
            generator.validate_packet(packet)

    def test_packet_cannot_upgrade_saved_evidence_to_candidate(self):
        packet = generator.create_packet(self.generate(), as_of=NOW)
        observed = packet["receipts"][0]["observation"]
        observed["observation"] = "API_ITEM_VISIBLE"
        observed["expected_content_id_match"] = True
        observed["affiliate_link_observed"] = True
        with self.assertRaisesRegex(generator.SavedReceiptError, "OVERCLAIMED"):
            generator.validate_packet(packet)

    def test_output_must_be_outside_repository(self):
        packet = generator.create_packet(self.generate(), as_of=NOW)
        with self.assertRaisesRegex(generator.SavedReceiptError, "OUTSIDE_REPOSITORY"):
            generator.write_isolated_packet(ROOT / "forbidden-packet.json", packet)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "packet.json"
            generator.write_isolated_packet(output, packet)
            restored = generator.validate_packet(json.loads(output.read_text(encoding="utf-8")))
            self.assertEqual(len(restored), 1)

    def test_source_has_no_api_or_secret_loading_path(self):
        source = (SCRIPTS / "generate-saved-lifecycle-receipts.py").read_text(encoding="utf-8")
        for forbidden in ("urlopen", "requests.", "load_secret", 'ROOT / ".env"'):
            self.assertNotIn(forbidden, source)
        self.assertIn("mode=ro", source)
        self.assertIn("PRAGMA query_only = ON", source)


if __name__ == "__main__":
    unittest.main()
