from datetime import datetime, timezone
from pathlib import Path
import hashlib
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_expansion_storage_commit as subject  # noqa: E402


NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def database(path: Path, run_id: str = "run"):
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE items(id INTEGER PRIMARY KEY,content_id TEXT);
        CREATE TABLE item_snapshots(id INTEGER PRIMARY KEY,item_id INTEGER,collection_run_id TEXT,source_offset INTEGER,source_position INTEGER);
        CREATE TABLE collection_runs(collection_run_id TEXT,run_type TEXT,started_at TEXT,status TEXT,max_items INTEGER,max_pages INTEGER,api_calls INTEGER,pages_fetched INTEGER,processed_items INTEGER,snapshots_inserted INTEGER,duplicate_content_ids_across_pages INTEGER);
        CREATE TABLE item_lifecycle_observations(snapshot_id INTEGER);
        CREATE TABLE item_snapshot_titles(snapshot_id INTEGER);
    """)
    connection.execute(
        "INSERT INTO collection_runs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (run_id,"native","2026-10-01T00:00:00Z","success",300,6,6,6,300,300,0),
    )
    for index in range(300):
        item_id = index + 1
        connection.execute("INSERT INTO items VALUES (?,?)", (item_id, f"cid-{run_id}-{item_id}"))
        connection.execute(
            "INSERT INTO item_snapshots VALUES (?,?,?,?,?)",
            (item_id,item_id,run_id,(index // 50) * 50 + 1,index % 50 + 1),
        )
    connection.commit()
    connection.close()


class ExpansionStorageCommitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.private = self.root / "private"
        self.private.mkdir()
        self.production = self.root / "production.db"
        database(self.production, "production")

    def tearDown(self):
        self.temp.cleanup()

    def staged(self, name="staged.db", run_id="run"):
        path = self.private / name
        database(path, run_id)
        return path

    def test_first_commit_is_atomic_collection_only_without_backup(self):
        staged = self.staged()
        expected = sha256(staged)
        result = subject.commit(
            staged, self.production, self.private,
            expected_candidate_sha256=expected, committed_at=NOW,
        )
        destination = self.private / subject.PRIMARY_NAME
        self.assertEqual(result.status, subject.COMMITTED)
        self.assertTrue(destination.is_file())
        self.assertFalse(staged.exists())
        self.assertEqual(sha256(destination), expected)
        self.assertFalse(result.backup_created)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_write_performed)

    def test_replacement_preserves_previous_generation(self):
        first = self.staged("first.db", "first")
        subject.commit(first, self.production, self.private, expected_candidate_sha256=sha256(first), committed_at=NOW)
        second = self.staged("second.db", "second")
        result = subject.commit(
            second, self.production, self.private,
            expected_candidate_sha256=sha256(second),
            committed_at=datetime(2026, 10, 2, tzinfo=timezone.utc),
        )
        self.assertEqual(result.status, subject.COMMITTED)
        self.assertTrue(result.backup_created)
        self.assertEqual(result.retained_backup_count, 1)

    def test_hash_mismatch_and_outside_path_block(self):
        staged = self.staged()
        result = subject.commit(
            staged, self.production, self.private,
            expected_candidate_sha256="0" * 64, committed_at=NOW,
        )
        self.assertEqual(result.status, subject.BLOCKED)
        outside = self.root / "outside.db"
        database(outside)
        result = subject.commit(
            outside, self.production, self.private,
            expected_candidate_sha256=sha256(outside), committed_at=NOW,
        )
        self.assertIn("STAGED_CANDIDATE_OUTSIDE_PRIVATE_ROOT", result.reason_codes)


if __name__ == "__main__":
    unittest.main()
