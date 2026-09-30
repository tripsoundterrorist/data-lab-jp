from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_expansion_disposable_db_rehearsal as subject  # noqa: E402


def database(path: Path, *, running: bool = False):
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE items(id INTEGER PRIMARY KEY, title TEXT);
        CREATE TABLE item_snapshots(id INTEGER PRIMARY KEY, item_id INTEGER);
        CREATE TABLE collection_runs(
          id INTEGER PRIMARY KEY, run_type TEXT, status TEXT, finished_at TEXT);
        INSERT INTO items VALUES (1, 'Fixture');
        INSERT INTO item_snapshots VALUES (1, 1);
    """)
    connection.execute(
        "INSERT INTO collection_runs VALUES (1,'native',?,?)",
        ("running" if running else "success", None if running else "2026-10-01T00:00:00Z"),
    )
    connection.commit()
    connection.close()


class DisposableDatabaseRehearsalTests(unittest.TestCase):
    def test_copy_restore_matches_and_source_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.db"
            database(path)
            before = path.read_bytes()
            result = subject.assess(path)
            after = path.read_bytes()
        self.assertEqual(result.status, subject.VERIFIED)
        self.assertEqual(result.item_count, 1)
        self.assertEqual(result.snapshot_count, 1)
        self.assertEqual(result.collection_run_count, 1)
        self.assertTrue(result.logical_digest_match)
        self.assertTrue(result.source_identity_preserved)
        self.assertFalse(result.temporary_files_retained)
        self.assertFalse(result.production_write_performed)
        self.assertEqual(result.api_calls, 0)
        self.assertEqual(before, after)

    def test_active_native_run_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.db"
            database(path, running=True)
            result = subject.assess(path)
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertEqual(result.reason_codes, ("ACTIVE_NATIVE_RUN",))

    def test_missing_source_blocks(self):
        result = subject.assess(Path("missing.db"))
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertEqual(result.reason_codes, ("SOURCE_INVALID",))

    def test_non_database_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.db"
            path.write_text("not sqlite", encoding="utf-8")
            result = subject.assess(path)
        self.assertEqual(result.status, subject.BLOCKED)


if __name__ == "__main__":
    unittest.main()
