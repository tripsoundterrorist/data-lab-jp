from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_lifecycle_receipt as receipt  # noqa: E402
import revenue_mvp_minimal_opaque_go_cta_packet as subject  # noqa: E402


STAMP = "2026-09-22T00:00:00Z"
NOW = datetime(2026, 9, 22, 1, 0, tzinfo=timezone.utc)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_database(path: Path, *, duplicate: bool = False) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript((ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO collection_runs (collection_run_id, run_type, status) "
            "VALUES ('r', 'legacy_migrated', 'unknown')"
        )
        count = 2 if duplicate else 1
        for value in range(1, count + 1):
            connection.execute(
                """INSERT INTO items
                (id, site, service, floor, content_id, title, first_observed_at,
                 last_observed_at, master_updated_at)
                VALUES (?, 'FANZA', 'digital', 'videoa', ?, 'mutable', ?, ?, ?)""",
                (value, f"private-content-{value}", STAMP, STAMP, STAMP),
            )
            connection.execute(
                """INSERT INTO item_snapshots
                (id, item_id, collection_run_id, observed_at, source_sort,
                 source_offset, source_position, price_min, query_context_json)
                VALUES (?, ?, 'r', ?, 'date', 1, ?, 1200, '{}')""",
                (value, value, STAMP, value),
            )
            connection.execute(
                """INSERT INTO item_lifecycle_observations
                (snapshot_id, contract_version, verification_mode, observation,
                 observed_at, expected_content_id_match, affiliate_link_observed,
                 source_status_code, inventory_signal, reason_code, created_at)
                VALUES (?, '0.1', 'COLLECTION_PAGE_ITEM', 'API_ITEM_VISIBLE', ?, 1,
                1, 200, 'UNKNOWN', 'AFFILIATE_URL_VALIDATED', ?)""",
                (value, STAMP, STAMP),
            )
            connection.execute(
                """INSERT INTO item_snapshot_titles
                (snapshot_id, contract_version, title, observed_at, created_at)
                VALUES (?, '0.1', 'immutable title', ?, ?)""",
                (value, STAMP, STAMP),
            )
        connection.commit()
    finally:
        connection.close()


class MinimalOpaqueGoCtaPacketTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = Path(self.temporary.name) / "data.db"
        create_database(self.database)

    def test_exact_candidate_is_bound_without_private_values(self):
        payload, result = subject.build_packet(self.database, digest(self.database), NOW)
        value = json.loads(payload)
        candidate = value["candidates"][0]
        expected = receipt.public_item_id(
            "FANZA", "digital", "videoa", "private-content-1"
        )
        self.assertEqual(candidate["public_id"], expected)
        self.assertEqual(candidate["cta_href"], f"/go/{expected}")
        self.assertEqual(candidate["disclosure_text"], "【PR】FANZAで確認")
        self.assertNotIn("private-content-1", payload.decode("utf-8"))
        self.assertEqual(result.status, subject.READY)
        self.assertTrue(all(not getattr(result, field) for field in (
            "publication_allowed", "production_activation_allowed",
            "affiliate_eligibility_allowed", "gate_mutation_allowed",
            "deployment_allowed", "network_io_performed", "production_write_performed",
        )))

    def test_stale_empty_or_duplicate_binding_fails_closed(self):
        with self.assertRaisesRegex(subject.CtaPacketFailure, "REVIEWED_CANDIDATE"):
            subject.build_packet(
                self.database, digest(self.database), NOW + timedelta(days=2)
            )
        duplicate = Path(self.temporary.name) / "duplicate.db"
        create_database(duplicate, duplicate=True)
        with self.assertRaisesRegex(subject.CtaPacketFailure, "BINDING_NOT_UNIQUE"):
            subject.build_packet(duplicate, digest(duplicate), NOW)

    def test_database_hash_mismatch_fails_closed(self):
        with self.assertRaises(Exception):
            subject.build_packet(self.database, "0" * 64, NOW)


if __name__ == "__main__":
    unittest.main()
