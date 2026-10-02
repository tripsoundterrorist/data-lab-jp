from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import category_collection_value_audit as subject  # noqa: E402


CONFIG = ROOT / "config" / "category-collection-v0.1.json"
SCHEMA = ROOT / "db" / "category-collection-schema.sql"


def build_database(path: Path) -> None:
    now = datetime.now(timezone.utc).isoformat()
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    targets = __import__("json").loads(CONFIG.read_text(encoding="utf-8"))["targets"]
    for index, target in enumerate(targets, 1):
        connection.execute(
            "INSERT INTO category_sources(source_id,content_type,site,service,floor,collection_mode) "
            "VALUES(?,?,?,?,?,'COLLECTION_ONLY')",
            (index, target["content_type"], target["site"], target["service"], target["floor"]),
        )
        run_id = f"run-{index}"
        connection.execute(
            "INSERT INTO category_collection_runs(run_id,source_id,started_at,finished_at,status,source_sort,requested_hits,fetched_items,response_sha256) "
            "VALUES(?,?,?,?, 'success','date',1,1,?)",
            (run_id, index, now, now, "0" * 64),
        )
        connection.execute(
            "INSERT INTO category_items(item_id,source_id,content_id,release_date_raw,contributors_json,series_json,genre_json,source_extension_json,first_observed_at,last_observed_at,normalizer_version) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (index, index, f"item-{index}", "2026-01-01", '{"maker":[]}', '[]', '[{"id":"1"}]', '{}', now, now, "0.1"),
        )
        connection.execute(
            "INSERT INTO category_item_snapshots(item_id,run_id,observed_at,current_price_min,list_price_min,discount_amount,source_sort,source_position,sanitized_raw_json) "
            "VALUES(?,?,?,?,?,?, 'date',1,'{}')",
            (index, run_id, now, 100, 200, 100),
        )
    connection.commit()
    connection.close()


class CategoryCollectionValueAuditTests(unittest.TestCase):
    def test_healthy_database_produces_aggregate_only_review(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "category.db"
            build_database(database)
            result = subject.assess(database, CONFIG)
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.source_count, 10)
        self.assertEqual(result.item_count, 10)
        self.assertEqual(result.snapshot_count, 10)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.database_write_performed)
        rendered = str(result.to_dict()).casefold()
        self.assertNotIn("content_id", rendered)
        self.assertNotIn("item-1", rendered)

    def test_price_change_is_counted_without_exposing_item_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "category.db"
            build_database(database)
            connection = sqlite3.connect(database)
            now = datetime.now(timezone.utc).isoformat()
            connection.execute(
                "INSERT INTO category_collection_runs(run_id,source_id,started_at,finished_at,status,source_sort,requested_hits,fetched_items,response_sha256) "
                "VALUES('run-change',1,?,?, 'success','date',1,1,?)",
                (now, now, "1" * 64),
            )
            connection.execute(
                "INSERT INTO category_item_snapshots(item_id,run_id,observed_at,current_price_min,source_sort,source_position,sanitized_raw_json) "
                "VALUES(1,'run-change',?,80,'date',1,'{}')",
                (now,),
            )
            connection.commit(); connection.close()
            result = subject.assess(database, CONFIG)
        doujin = next(row for row in result.categories if row.content_type == "doujin")
        self.assertEqual(doujin.items_with_price_change, 1)

    def test_unhealthy_or_missing_database_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subject.assess(Path(directory) / "missing.db", CONFIG)
        self.assertEqual(result.status, subject.FAIL_CLOSED)
        self.assertFalse(result.publication_allowed)


if __name__ == "__main__":
    unittest.main()
