from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_product_refresh_preapproval as subject  # noqa: E402
from revenue_mvp_lifecycle_receipt import public_item_id  # noqa: E402


OLD = "2026-09-29T00:00:00Z"
NEW = "2026-09-30T00:00:00Z"
NOW = datetime(2026, 9, 30, 1, tzinfo=timezone.utc)


class ProductRefreshPreapprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.db = root / "fixture.db"
        self.source = root / "current.html"
        self.d1 = root / "d1.sql"
        self.output = root / "candidate.html"
        self.source.write_text(
            '<article class="item"><h2>旧商品</h2><p class="price">1,000円</p>'
            f'<time>{OLD}</time></article>',
            encoding="utf-8",
        )
        with sqlite3.connect(self.db) as connection:
            connection.executescript((ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))
            for run_id, stamp in (("old-run", OLD), ("new-run", NEW)):
                connection.execute(
                    """INSERT INTO collection_runs
                       (collection_run_id,run_type,started_at,finished_at,
                        first_observed_at,last_observed_at,status,processed_items,
                        snapshots_inserted,api_calls,pages_fetched,site,service,floor,
                        source_sort,hits,max_items,max_pages,api_total_count_initial,
                        total_count_changed,fetched_items,duplicate_content_ids_across_pages,
                        items_upserted,collection_complete,stop_reason)
                       VALUES (?,'native',?,?,?,?, 'success',1,1,1,1,'FANZA',
                        'digital','videoa','date',50,1,1,1,0,1,0,1,0,'max_items')""",
                    (run_id, stamp, stamp, stamp, stamp),
                )
            for item_id, content_id, title, stamp, run_id in (
                (1, "old-001", "旧商品", OLD, "old-run"),
                (2, "new-001", "新商品", NEW, "new-run"),
            ):
                connection.execute(
                    """INSERT INTO items
                       (id,site,service,floor,content_id,title,image_url_large,
                        first_observed_at,last_observed_at,master_updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (item_id, "FANZA", "digital", "videoa", content_id, title,
                     f"https://pics.dmm.co.jp/{content_id}.jpg", stamp, stamp, stamp),
                )
                connection.execute(
                    """INSERT INTO item_snapshots
                       (id,item_id,collection_run_id,observed_at,source_sort,
                        source_offset,source_position,price_min,query_context_json)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (item_id, item_id, run_id, stamp, "date", 1, 1, 1000, "{}"),
                )
                connection.execute(
                    "INSERT INTO item_snapshot_titles VALUES (?,?,?,?,?)",
                    (item_id, "0.1", title, stamp, stamp),
                )
                connection.execute(
                    """INSERT INTO item_lifecycle_observations
                       (snapshot_id,contract_version,verification_mode,observation,
                        observed_at,expected_content_id_match,affiliate_link_observed,
                        source_status_code,inventory_signal,reason_code,created_at)
                       VALUES (?,'0.1','COLLECTION_PAGE_ITEM','API_ITEM_VISIBLE',?,
                        1,1,200,'UNKNOWN','AFFILIATE_URL_VALIDATED',?)""",
                    (item_id, stamp, stamp),
                )
        new_public_id = public_item_id("FANZA", "digital", "videoa", "new-001")
        self.d1.write_text(
            "PRAGMA defer_foreign_keys=TRUE;\n"
            "INSERT INTO affiliate_item_lookup "
            "(public_id,content_id,rights_status,lifecycle_status,verification_status,affiliate_enabled,updated_at) "
            f"VALUES ('{new_public_id}','new-001','CONDITIONALLY_APPROVED','RESOLVED','PASS',1,'2026-09-30T00:30:00Z');\n"
            "INSERT INTO affiliate_redirect_target (public_id,content_id,affiliate_url,verified_at) "
            f"VALUES ('{new_public_id}','new-001','https://example.invalid/affiliate','2026-09-30T00:30:00Z');\n"
            "INSERT INTO affiliate_lifecycle_revalidation_event "
            "(id,public_id,checked_at,outcome,affiliate_enabled_after,reason_code) "
            f"VALUES (1,'{new_public_id}','2026-09-30T00:30:00Z','VALID',1,'VALID');\n",
            encoding="utf-8",
        )

    def assess(self):
        return subject.assess(
            self.source, self.db, self.d1, self.output,
            expected_db_sha256=hashlib.sha256(self.db.read_bytes()).hexdigest(),
            expected_d1_sha256=hashlib.sha256(self.d1.read_bytes()).hexdigest(),
            evaluated_at=NOW, expected_count=1,
        )

    def test_builds_only_a_fully_covered_preapproval_candidate(self):
        result = self.assess()
        self.assertEqual(result.status, subject.READY)
        self.assertEqual((result.retained_count, result.added_count, result.removed_count), (0, 1, 1))
        self.assertEqual(
            (result.d1_lookup_matches, result.d1_eligible_matches,
             result.d1_redirect_matches, result.d1_runtime_redirect_matches),
            (1, 1, 1, 1),
        )
        self.assertEqual(result.new_routes_freshly_revalidated, 1)
        self.assertTrue(result.candidate_written)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_write_performed)
        self.assertFalse(result.d1_write_performed)
        self.assertTrue(result.explicit_user_approval_required)

    def test_missing_runtime_target_fails_closed_and_deletes_candidate(self):
        self.d1.write_text(
            "\n".join(line for line in self.d1.read_text(encoding="utf-8").splitlines()
                      if "affiliate_redirect_target" not in line and "example.invalid" not in line) + "\n",
            encoding="utf-8",
        )
        result = self.assess()
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertEqual(result.reason_codes, ("D1_RUNTIME_COVERAGE_INCOMPLETE",))
        self.assertFalse(self.output.exists())

    def test_identity_mismatch_fails_before_output(self):
        result = subject.assess(
            self.source, self.db, self.d1, self.output,
            expected_db_sha256="0" * 64,
            expected_d1_sha256=hashlib.sha256(self.d1.read_bytes()).hexdigest(),
            evaluated_at=NOW, expected_count=1,
        )
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
