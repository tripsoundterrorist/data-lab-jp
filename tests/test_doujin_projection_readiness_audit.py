from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import category_collection_health as health  # noqa: E402
import doujin_projection_readiness_audit as subject  # noqa: E402


SCHEMA = ROOT / "db" / "category-collection-schema.sql"
CONFIG = ROOT / "config" / "category-collection-v0.1.json"


def build_database(path: Path, *, missing_title: bool = False) -> None:
    now = datetime.now(timezone.utc).isoformat()
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    for index, content_type in enumerate(("doujin", "doujin_bl", "doujin_tl"), 1):
        connection.execute(
            "INSERT INTO category_sources(source_id,content_type,site,service,floor,collection_mode) "
            "VALUES(?,?, 'FANZA','doujin',?,'COLLECTION_ONLY')",
            (index, content_type, f"floor-{index}"),
        )
        connection.execute(
            "INSERT INTO category_collection_runs(run_id,source_id,started_at,finished_at,status,source_sort,requested_hits,fetched_items,response_sha256) "
            "VALUES(?,?,?,?, 'success','date',1,1,?)",
            (f"run-{index}", index, now, now, "0" * 64),
        )
        connection.execute(
            "INSERT INTO category_items(item_id,source_id,content_id,title,release_date_raw,item_url,image_json,contributors_json,series_json,genre_json,source_extension_json,first_observed_at,last_observed_at,normalizer_version) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (index, index, f"item-{index}", None if missing_title and index == 1 else "Title",
             "2026-01-01", "https://example.invalid/item", '{"large":"https://example.invalid/image.jpg","list":null}',
             '{"maker":[{"id":"1","name":"Maker"}]}', '[]', '[{"id":"2","name":"Genre"}]',
             '{}', now, now, "0.1"),
        )
        connection.execute(
            "INSERT INTO category_item_snapshots(item_id,run_id,observed_at,current_price_min,list_price_min,discount_amount,discount_rate,source_sort,source_position,sanitized_raw_json) "
            "VALUES(?,?,?,?,?,?,?,?,1,'{}')",
            (index, f"run-{index}", now, 100, 200, 100, 50.0, "date"),
        )
    connection.commit()
    connection.close()


def healthy_result():
    return mock.Mock(status=health.HEALTHY)


class DoujinProjectionReadinessAuditTests(unittest.TestCase):
    def test_counts_ready_rows_without_creating_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "category.db"
            build_database(database)
            with mock.patch.object(subject.health, "assess", return_value=healthy_result()):
                result = subject.assess(database, CONFIG)
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.item_count, 3)
        self.assertEqual(result.structure_ready_count, 3)
        self.assertEqual(result.structure_blocked_count, 0)
        self.assertFalse(result.artifact_created)
        self.assertFalse(result.publication_allowed)

    def test_invalid_row_is_counted_without_identity_output(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "category.db"
            build_database(database, missing_title=True)
            with mock.patch.object(subject.health, "assess", return_value=healthy_result()):
                result = subject.assess(database, CONFIG)
        self.assertEqual(result.structure_ready_count, 2)
        self.assertEqual(result.structure_blocked_count, 1)
        self.assertIn("STRUCTURE_BLOCKERS_PRESENT", result.reason_codes)
        rendered = str(result.to_dict())
        self.assertNotIn("item-1", rendered)
        self.assertNotIn("Title", rendered)

    def test_unhealthy_collection_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(subject.health, "assess", return_value=mock.Mock(status=health.FAIL_CLOSED)):
                result = subject.assess(Path(directory) / "missing.db", CONFIG)
        self.assertEqual(result.status, subject.FAIL_CLOSED)
        self.assertFalse(result.publication_allowed)


if __name__ == "__main__":
    unittest.main()
