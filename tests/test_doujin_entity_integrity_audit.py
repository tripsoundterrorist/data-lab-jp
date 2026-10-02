from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import doujin_entity_integrity_audit as subject  # noqa: E402


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
        connection.execute(
            "INSERT INTO category_collection_runs(run_id,source_id,started_at,finished_at,status,source_sort,requested_hits,fetched_items,response_sha256) "
            "VALUES(?,?,?,?, 'success','date',1,1,?)",
            (f"run-{index}", index, now, now, "0" * 64),
        )
        connection.execute(
            "INSERT INTO category_items(item_id,source_id,content_id,contributors_json,series_json,genre_json,source_extension_json,first_observed_at,last_observed_at,normalizer_version) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (index, index, f"item-{index}", '{"maker":[{"id":"10","name":"Maker"}]}',
             '[{"id":"20","name":"Series"}]', '[{"id":"30","name":"Genre"}]',
             '{}', now, now, "0.1"),
        )
        connection.execute(
            "INSERT INTO category_item_snapshots(item_id,run_id,observed_at,source_sort,source_position,sanitized_raw_json) "
            "VALUES(?,?,?,'date',1,'{}')",
            (index, f"run-{index}", now),
        )
    connection.commit()
    connection.close()


class DoujinEntityIntegrityAuditTests(unittest.TestCase):
    def test_reports_aggregates_without_entity_values(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "category.db"
            build_database(database)
            result = subject.assess(database, CONFIG)
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.item_count, 3)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.database_write_performed)
        self.assertTrue(all(row.entries_with_id_and_name == 3 for row in result.entities))
        rendered = str(result.to_dict())
        self.assertNotIn("Maker", rendered)
        self.assertNotIn("item-1", rendered)

    def test_incomplete_reference_is_counted_and_remains_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "category.db"
            build_database(database)
            connection = sqlite3.connect(database)
            connection.execute(
                "UPDATE category_items SET series_json='[{\"id\":\"\",\"name\":\"Series\"}]' "
                "WHERE item_id=1"
            )
            connection.commit()
            connection.close()
            result = subject.assess(database, CONFIG)
        series = next(row for row in result.entities if row.entity_type == "series")
        self.assertEqual(series.malformed_entry_count, 1)
        self.assertIn("ENTITY_REFERENCE_INTEGRITY_GAPS_PRESENT", result.reason_codes)
        self.assertFalse(result.publication_allowed)

    def test_missing_database_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subject.assess(Path(directory) / "missing.db", CONFIG)
        self.assertEqual(result.status, subject.FAIL_CLOSED)
        self.assertFalse(result.publication_allowed)


if __name__ == "__main__":
    unittest.main()
