from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_public_expansion_coverage as subject  # noqa: E402


NOW = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)


def database(path: Path, rows: int, *, stale: bool = False, missing_image: bool = False):
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE items(id INTEGER PRIMARY KEY, image_url_large TEXT);
        CREATE TABLE item_snapshots(
          id INTEGER PRIMARY KEY, item_id INTEGER, observed_at TEXT, price_min INTEGER);
        CREATE TABLE item_snapshot_titles(snapshot_id INTEGER, observed_at TEXT, title TEXT);
        CREATE TABLE item_lifecycle_observations(
          snapshot_id INTEGER, affiliate_link_observed INTEGER,
          source_status_code INTEGER, reason_code TEXT);
    """)
    observed = "2026-09-28T00:00:00Z" if stale else "2026-09-30T12:00:00Z"
    for index in range(1, rows + 1):
        image = None if missing_image and index == rows else "https://pics.dmm.co.jp/item.jpg"
        connection.execute("INSERT INTO items VALUES (?,?)", (index, image))
        connection.execute(
            "INSERT INTO item_snapshots VALUES (?,?,?,?)", (index, index, observed, 1000)
        )
        connection.execute(
            "INSERT INTO item_snapshot_titles VALUES (?,?,?)", (index, observed, "Title")
        )
        connection.execute(
            "INSERT INTO item_lifecycle_observations VALUES (?,?,?,?)",
            (index, 1, 200, "AFFILIATE_URL_VALIDATED"),
        )
    connection.commit()
    connection.close()


class ExpansionCoverageTests(unittest.TestCase):
    def test_less_than_300_fresh_eligible_items_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.db"
            database(path, 120)
            result = subject.assess(path, evaluated_at=NOW)
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertEqual(result.fresh_base_eligible_count, 120)
        self.assertEqual(result.target_gap, 180)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_write_performed)
        self.assertFalse(result.candidate_ids_exposed)

    def test_exact_coverage_reaches_separate_review_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.db"
            database(path, 300)
            result = subject.assess(path, evaluated_at=NOW)
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.target_gap, 0)
        self.assertIn("SEPARATE_EXACT_SELECTION_REQUIRED", result.reason_codes)
        self.assertFalse(result.publication_allowed)

    def test_stale_rows_are_not_fresh(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.db"
            database(path, 300, stale=True)
            result = subject.assess(path, evaluated_at=NOW)
        self.assertEqual(result.base_eligible_count, 300)
        self.assertEqual(result.fresh_base_eligible_count, 0)
        self.assertEqual(result.status, subject.BLOCKED)

    def test_missing_image_reduces_eligibility(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.db"
            database(path, 300, missing_image=True)
            result = subject.assess(path, evaluated_at=NOW)
        self.assertEqual(result.official_image_count, 299)
        self.assertEqual(result.fresh_base_eligible_count, 299)
        self.assertEqual(result.status, subject.BLOCKED)

    def test_invalid_input_fails_closed(self):
        result = subject.assess(Path("missing.db"), evaluated_at=NOW)
        self.assertEqual(result.status, subject.FAIL_CLOSED)


if __name__ == "__main__":
    unittest.main()
