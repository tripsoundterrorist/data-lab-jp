from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "unordered_review_packet", ROOT / "scripts" / "revenue_mvp_unordered_review_packet.py"
)
assert spec is not None and spec.loader is not None
packet = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = packet
spec.loader.exec_module(packet)

STAMP = "2026-09-22T00:00:00Z"
NOW = datetime(2026, 9, 22, 1, 0, tzinfo=timezone.utc)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_database(path: Path, *, title_stamp: str = STAMP) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript((ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO collection_runs (collection_run_id, run_type, status) VALUES ('r', 'legacy_migrated', 'unknown')"
        )
        connection.execute(
            """INSERT INTO items
            (id, site, service, floor, content_id, title, first_observed_at,
             last_observed_at, master_updated_at)
            VALUES (1, 'FANZA', 'digital', 'videoa', 'secret-content-id',
            'mutable title must not be used', ?, ?, ?)""",
            (STAMP, STAMP, STAMP),
        )
        connection.execute(
            """INSERT INTO item_snapshots
            (id, item_id, collection_run_id, observed_at, source_sort,
             source_offset, source_position, price_min, query_context_json)
            VALUES (1, 1, 'r', ?, 'date', 1, 1, 1200, '{}')""",
            (STAMP,),
        )
        connection.execute(
            """INSERT INTO item_lifecycle_observations
            (snapshot_id, contract_version, verification_mode, observation,
             observed_at, expected_content_id_match, affiliate_link_observed,
             source_status_code, inventory_signal, reason_code, created_at)
            VALUES (1, '0.1', 'COLLECTION_PAGE_ITEM', 'API_ITEM_VISIBLE', ?, 1,
            1, 200, 'UNKNOWN', 'AFFILIATE_URL_VALIDATED', ?)""",
            (STAMP, STAMP),
        )
        connection.execute(
            """INSERT INTO item_snapshot_titles
            (snapshot_id, contract_version, title, observed_at, created_at)
            VALUES (1, '0.1', 'immutable snapshot title', ?, ?)""",
            (title_stamp, title_stamp),
        )
        connection.commit()
    finally:
        connection.close()


class UnorderedReviewPacketTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.database = self.root / "data.db"
        create_database(self.database)

    def test_valid_saved_evidence_builds_review_only_candidate(self):
        payload = packet.build_packet(self.database, sha256(self.database), NOW)
        value = json.loads(payload)
        self.assertEqual(len(value["candidates"]), 1)
        candidate = value["candidates"][0]
        self.assertEqual(candidate["title"], "immutable snapshot title")
        self.assertEqual(candidate["current_price"], 1200)
        self.assertEqual(candidate["api_observed_at"], STAMP)
        self.assertNotIn("mutable title", payload.decode("utf-8"))
        self.assertNotIn("secret-content-id", payload.decode("utf-8"))
        for key in (
            "publication_allowed", "production_activation_allowed",
            "affiliate_eligibility_allowed", "gate_mutation_allowed", "cta_allowed",
        ):
            self.assertFalse(value[key])
        self.assertFalse(set(candidate) & packet.FORBIDDEN_KEYS)

    def test_stale_evidence_is_not_a_candidate(self):
        payload = packet.build_packet(
            self.database, sha256(self.database), NOW + timedelta(days=2)
        )
        self.assertEqual(json.loads(payload)["candidates"], [])

    def test_timestamp_mismatch_and_hash_mismatch_fail_closed(self):
        mismatched = self.root / "mismatch.db"
        create_database(mismatched, title_stamp="2026-09-22T00:00:01Z")
        payload = packet.build_packet(mismatched, sha256(mismatched), NOW)
        self.assertEqual(json.loads(payload)["candidates"], [])
        with self.assertRaisesRegex(packet.PacketFailure, "DATABASE_IDENTITY_INVALID"):
            packet.build_packet(self.database, "0" * 64, NOW)

    def test_output_is_explicit_atomic_and_outside_repository(self):
        target = self.root / "review.json"
        result = packet.run(self.database, sha256(self.database), NOW, target)
        self.assertTrue(result.output_written)
        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), result.packet_sha256)
        with self.assertRaisesRegex(packet.PacketFailure, "OUTPUT_MUST_BE_OUTSIDE_REPOSITORY"):
            packet.run(
                self.database,
                sha256(self.database),
                NOW,
                ROOT / "runtime" / "forbidden-review.json",
            )


if __name__ == "__main__":
    unittest.main()
