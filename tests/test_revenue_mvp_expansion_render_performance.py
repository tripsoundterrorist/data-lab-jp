import hashlib
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_expansion_render_performance as subject  # noqa: E402


def database(path: Path, *, count: int = 300) -> None:
    connection = sqlite3.connect(path)
    connection.executescript("""
      CREATE TABLE collection_runs(
        collection_run_id TEXT,run_type TEXT,started_at TEXT,status TEXT,
        max_items INTEGER,max_pages INTEGER,api_calls INTEGER,pages_fetched INTEGER,
        processed_items INTEGER,snapshots_inserted INTEGER,
        duplicate_content_ids_across_pages INTEGER);
      CREATE TABLE item_snapshots(
        id INTEGER PRIMARY KEY,collection_run_id TEXT,observed_at TEXT,
        source_offset INTEGER,source_position INTEGER,price_min INTEGER);
      CREATE TABLE item_snapshot_titles(snapshot_id INTEGER,title TEXT);
    """)
    connection.execute(
        "INSERT INTO collection_runs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("run", "native", "2026-10-02T00:00:00Z", "success", 300, 6, 6, 6,
         count, count, 0),
    )
    for index in range(count):
        connection.execute(
            "INSERT INTO item_snapshots VALUES (?,?,?,?,?,?)",
            (index + 1, "run", "2026-10-02T00:00:00Z",
             1 + (index // 50) * 50, 1 + index % 50, 1000 + index),
        )
        connection.execute(
            "INSERT INTO item_snapshot_titles VALUES (?,?)",
            (index + 1, f"架空の検証用商品 {index + 1}"),
        )
    connection.commit()
    connection.close()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ExpansionRenderPerformanceTests(unittest.TestCase):
    def test_exact_300_candidate_is_verified_without_output_or_permission(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.db"
            database(path)
            result = subject.verify(path, expected_database_sha256=digest(path))
        self.assertEqual(result.status, subject.VERIFIED)
        self.assertEqual(result.candidate_item_count, 300)
        self.assertTrue(result.deterministic_output)
        self.assertTrue(result.rendered_structure_verified)
        self.assertFalse(result.candidate_identifiers_exposed)
        self.assertFalse(result.output_written)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_write_allowed)
        self.assertFalse(result.deployment_allowed)

    def test_hash_mismatch_and_non_exact_candidate_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.db"
            database(path)
            self.assertEqual(
                subject.verify(path, expected_database_sha256="0" * 64).status,
                subject.BLOCKED,
            )
            path.unlink()
            database(path, count=299)
            self.assertEqual(
                subject.verify(path, expected_database_sha256=digest(path)).status,
                subject.BLOCKED,
            )


if __name__ == "__main__":
    unittest.main()
