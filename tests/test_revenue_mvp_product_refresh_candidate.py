from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_product_refresh_candidate as subject  # noqa: E402


STAMP = "2026-09-30T00:00:00Z"
NOW = datetime(2026, 9, 30, 1, tzinfo=timezone.utc)


class ProductRefreshCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.db = root / "fixture.db"
        self.output = root / "candidate.html"
        with sqlite3.connect(self.db) as connection:
            connection.executescript(
                (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
            )
            connection.execute("""
                INSERT INTO collection_runs
                (collection_run_id,run_type,started_at,finished_at,
                 first_observed_at,last_observed_at,status,processed_items,
                 snapshots_inserted,api_calls,pages_fetched,site,service,floor,
                 source_sort,hits,max_items,max_pages,api_total_count_initial,
                 total_count_changed,fetched_items,duplicate_content_ids_across_pages,
                 items_upserted,collection_complete,stop_reason)
                VALUES ('run','native',?,?,?,?,'success',1,1,1,1,'FANZA',
                 'digital','videoa','date',50,1,1,1,0,1,0,1,0,'max_items')
            """, (STAMP, STAMP, STAMP, STAMP))
            connection.execute("""
                INSERT INTO items
                (id,site,service,floor,content_id,title,image_url_large,
                 first_observed_at,last_observed_at,master_updated_at)
                VALUES (1,'FANZA','digital','videoa','fixture-001','mutable',
                 'https://pics.dmm.co.jp/fixture.jpg',?,?,?)
            """, (STAMP, STAMP, STAMP))
            connection.execute("""
                INSERT INTO item_snapshots
                (id,item_id,collection_run_id,observed_at,source_sort,
                 source_offset,source_position,price_min,query_context_json)
                VALUES (1,1,'run',?,'date',1,1,1200,'{}')
            """, (STAMP,))
            connection.execute("""
                INSERT INTO item_snapshot_titles
                (snapshot_id,contract_version,title,observed_at,created_at)
                VALUES (1,'0.1','架空の商品',?,?)
            """, (STAMP, STAMP))
            connection.execute("""
                INSERT INTO item_lifecycle_observations
                (snapshot_id,contract_version,verification_mode,observation,
                 observed_at,expected_content_id_match,affiliate_link_observed,
                 source_status_code,inventory_signal,reason_code,created_at)
                VALUES (1,'0.1','COLLECTION_PAGE_ITEM','API_ITEM_VISIBLE',?,
                 1,1,200,'UNKNOWN','AFFILIATE_URL_VALIDATED',?)
            """, (STAMP, STAMP))

    def digest(self):
        return hashlib.sha256(self.db.read_bytes()).hexdigest()

    def test_builds_exact_offline_candidate_with_all_ctas(self):
        result = subject.build_candidate(
            self.db, self.digest(), NOW, self.output, expected_count=1
        )
        self.assertEqual(result.status, subject.READY)
        self.assertEqual((result.card_count, result.image_count, result.cta_count), (1, 1, 1))
        self.assertEqual(result.go_route_count, 1)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_write_performed)
        self.assertFalse(result.d1_write_performed)
        self.assertEqual(hashlib.sha256(self.output.read_bytes()).hexdigest(), result.candidate_sha256)

    def test_wrong_identity_or_count_fails_without_output(self):
        for digest, count in (("0" * 64, 1), (self.digest(), 2)):
            with self.subTest(digest=digest, count=count):
                result = subject.build_candidate(
                    self.db, digest, NOW, self.output, expected_count=count
                )
                self.assertEqual(result.status, subject.BLOCKED)
                self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
