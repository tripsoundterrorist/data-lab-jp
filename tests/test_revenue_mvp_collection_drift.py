import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_collection_drift as drift  # noqa: E402


def fixture(directory: str, count: int = 2) -> tuple[Path, Path]:
    database = Path(directory) / "data.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE items(id INTEGER PRIMARY KEY)")
    connection.executemany("INSERT INTO items(id) VALUES(?)", [(x,) for x in range(count)])
    connection.commit(); connection.close()
    receipt = Path(directory) / "receipt.json"
    receipt.write_text(json.dumps({
        "item_count": count,
        "source_db_sha256": hashlib.sha256(database.read_bytes()).hexdigest(),
        "publication_allowed": False,
        "production_write_performed": False,
        "gate_unlock_allowed": False,
    }), encoding="utf-8")
    return database, receipt


class RevenueMvpCollectionDriftTests(unittest.TestCase):
    def test_exact_state_is_in_sync(self):
        with tempfile.TemporaryDirectory() as directory:
            database, receipt = fixture(directory)
            result = drift.assess(database, receipt, 2)
        self.assertEqual(drift.IN_SYNC, result.status)
        self.assertFalse(result.artifact_refresh_required)
        self.assertFalse(result.d1_lookup_refresh_required)
        self.assertFalse(result.publication_allowed)

    def test_snapshot_only_change_requires_artifact_not_d1(self):
        with tempfile.TemporaryDirectory() as directory:
            database, receipt = fixture(directory)
            connection = sqlite3.connect(database)
            connection.execute("CREATE TABLE observations(id INTEGER)")
            connection.commit(); connection.close()
            result = drift.assess(database, receipt, 2)
        self.assertEqual(drift.SYNC_REQUIRED, result.status)
        self.assertTrue(result.artifact_refresh_required)
        self.assertFalse(result.d1_lookup_refresh_required)

    def test_new_item_requires_both_refreshes(self):
        with tempfile.TemporaryDirectory() as directory:
            database, receipt = fixture(directory)
            connection = sqlite3.connect(database)
            connection.execute("INSERT INTO items VALUES(3)")
            connection.commit(); connection.close()
            result = drift.assess(database, receipt, 2)
        self.assertEqual(drift.SYNC_REQUIRED, result.status)
        self.assertTrue(result.artifact_refresh_required)
        self.assertTrue(result.d1_lookup_refresh_required)
        self.assertFalse(result.production_write_performed)

    def test_non_monotonic_or_permissive_input_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            database, receipt = fixture(directory)
            self.assertEqual(drift.FAIL_CLOSED, drift.assess(database, receipt, 3).status)
            value = json.loads(receipt.read_text())
            value["publication_allowed"] = True
            receipt.write_text(json.dumps(value))
            self.assertEqual(drift.FAIL_CLOSED, drift.assess(database, receipt, 2).status)


if __name__ == "__main__":
    unittest.main()
