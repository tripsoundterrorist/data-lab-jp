from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_expansion_storage_gate as subject  # noqa: E402


class ExpansionStorageGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.private = self.root / "runtime" / "private"
        self.private.mkdir(parents=True)
        self.candidate = self.private / "expansion.db"
        self.production = self.root / "production.db"
        self._database(self.candidate, 300)
        self._database(self.production, 100)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _database(path: Path, run_items: int):
        connection = sqlite3.connect(path)
        connection.executescript("""
            CREATE TABLE items(id INTEGER PRIMARY KEY,content_id TEXT);
            CREATE TABLE item_snapshots(id INTEGER PRIMARY KEY,item_id INTEGER,collection_run_id TEXT,source_offset INTEGER,source_position INTEGER);
            CREATE TABLE collection_runs(collection_run_id TEXT,run_type TEXT,started_at TEXT,status TEXT,max_items INTEGER,max_pages INTEGER,api_calls INTEGER,pages_fetched INTEGER,processed_items INTEGER,snapshots_inserted INTEGER,duplicate_content_ids_across_pages INTEGER);
            CREATE TABLE item_lifecycle_observations(snapshot_id INTEGER);
            CREATE TABLE item_snapshot_titles(snapshot_id INTEGER);
        """)
        pages = 6 if run_items == 300 else 2
        connection.execute(
            "INSERT INTO collection_runs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("run","native","2026-10-01T00:00:00Z","success",run_items,pages,pages,pages,run_items,run_items,0),
        )
        for index in range(run_items):
            item_id = index + 1
            offset = (index // 50) * 50 + 1
            position = index % 50 + 1
            connection.execute("INSERT INTO items VALUES (?,?)", (item_id, f"cid-{item_id}"))
            connection.execute("INSERT INTO item_snapshots VALUES (?,?,?,?,?)", (item_id,item_id,"run",offset,position))
        connection.commit()
        connection.close()

    def boundary(self, **changes):
        values = {
            "candidate_path": self.candidate,
            "production_database_path": self.production,
            "private_root": self.private,
            "retention_count": 7,
            "raw_payload_retained": False,
            "publication_connected": False,
            "sitemap_connected": False,
            "d1_connected": False,
        }
        values.update(changes)
        return subject.StorageBoundary(**values)

    def test_exact_private_300_item_candidate_is_retention_ready_only(self):
        result = subject.assess(self.boundary())
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.latest_run_item_count, 300)
        self.assertEqual(result.latest_run_api_calls, 6)
        self.assertEqual(result.backup_retention_count, 7)
        self.assertTrue(result.collection_only)
        self.assertFalse(result.candidate_ids_exposed)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_write_allowed)

    def test_production_path_and_publication_connections_block(self):
        result = subject.assess(self.boundary(candidate_path=self.production))
        self.assertIn("PRIVATE_STORAGE_BOUNDARY_INVALID", result.reason_codes)
        result = subject.assess(self.boundary(publication_connected=True))
        self.assertIn("PUBLICATION_CONNECTION_FORBIDDEN", result.reason_codes)

    def test_raw_payload_and_wrong_retention_block(self):
        self.assertIn(
            "RAW_PAYLOAD_RETENTION_FORBIDDEN",
            subject.assess(self.boundary(raw_payload_retained=True)).reason_codes,
        )
        self.assertIn(
            "RETENTION_COUNT_INVALID",
            subject.assess(self.boundary(retention_count=30)).reason_codes,
        )

    def test_non_300_latest_run_blocks(self):
        result = subject.assess(self.boundary(candidate_path=self.production))
        self.assertEqual(result.status, subject.BLOCKED)

    def test_invalid_contract_blocks(self):
        self.assertEqual(subject.assess({}).status, subject.BLOCKED)


if __name__ == "__main__":
    unittest.main()
