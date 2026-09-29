from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_product_refresh_rehearsal as subject  # noqa: E402


OLD = "2026-09-29T00:00:00Z"
NEW = "2026-09-30T00:00:00Z"


class ProductRefreshRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.db = root / "fixture.db"
        self.source = root / "items.html"
        self.source.write_text(
            '<article class="item"><h2>旧商品</h2>'
            '<p class="price">1,000円</p><time>' + OLD + '</time></article>',
            encoding="utf-8",
        )
        with sqlite3.connect(self.db) as connection:
            connection.executescript("""
                CREATE TABLE items (id INTEGER PRIMARY KEY, site TEXT, service TEXT,
                  floor TEXT, content_id TEXT, image_url_large TEXT);
                CREATE TABLE item_snapshots (id INTEGER PRIMARY KEY, item_id INTEGER,
                  collection_run_id TEXT, observed_at TEXT, source_position INTEGER,
                  price_min INTEGER);
                CREATE TABLE item_snapshot_titles (snapshot_id INTEGER, title TEXT,
                  observed_at TEXT);
                CREATE TABLE item_lifecycle_observations (snapshot_id INTEGER,
                  affiliate_link_observed INTEGER, source_status_code INTEGER);
                CREATE TABLE collection_runs (collection_run_id TEXT, run_type TEXT,
                  started_at TEXT, status TEXT, processed_items INTEGER,
                  snapshots_inserted INTEGER, api_calls INTEGER, pages_fetched INTEGER);
            """)
            for item_id, content_id, title, stamp, run_id in (
                (1, "old-001", "旧商品", OLD, "old-run"),
                (2, "new-001", "新商品", NEW, "new-run"),
            ):
                connection.execute(
                    "INSERT INTO items VALUES (?,?,?,?,?,?)",
                    (item_id, "FANZA", "digital", "videoa", content_id,
                     f"https://pics.dmm.co.jp/{content_id}.jpg"),
                )
                connection.execute(
                    "INSERT INTO item_snapshots VALUES (?,?,?,?,?,1000)",
                    (item_id, item_id, run_id, stamp, 1),
                )
                connection.execute(
                    "INSERT INTO item_snapshot_titles VALUES (?,?,?)",
                    (item_id, title, stamp),
                )
                connection.execute(
                    "INSERT INTO item_lifecycle_observations VALUES (?,1,200)",
                    (item_id,),
                )
            connection.execute(
                "INSERT INTO collection_runs VALUES (?,?,?,?,?,?,?,?)",
                ("new-run", "native", NEW, "success", 1, 1, 1, 1),
            )

    def assess(self):
        return subject.assess(
            self.source, self.db, expected_count=1,
            evaluated_at=datetime(2026, 9, 30, 1, tzinfo=timezone.utc),
        )

    def test_reports_aggregate_rotation_without_publication(self):
        result = self.assess()
        self.assertEqual(result.status, "READY_FOR_SEPARATE_REFRESH_CANDIDATE")
        self.assertEqual((result.retained_count, result.added_count, result.removed_count), (0, 1, 1))
        self.assertEqual(result.affiliate_eligible_count, 1)
        self.assertTrue(result.d1_refresh_required)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_write_performed)

    def test_missing_affiliate_observation_fails_closed(self):
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                "UPDATE item_lifecycle_observations SET affiliate_link_observed=0 WHERE snapshot_id=2"
            )
        self.assertEqual(self.assess().status, "BLOCKED")

    def test_stale_candidate_fails_closed(self):
        result = subject.assess(
            self.source, self.db, expected_count=1,
            evaluated_at=datetime(2026, 10, 3, tzinfo=timezone.utc),
        )
        self.assertEqual(result.status, "BLOCKED")


if __name__ == "__main__":
    unittest.main()
