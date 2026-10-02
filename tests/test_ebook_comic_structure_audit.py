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
import ebook_comic_structure_audit as subject  # noqa: E402


SCHEMA = ROOT / "db" / "category-collection-schema.sql"
CONFIG = ROOT / "config" / "category-collection-v0.1.json"


def build_database(path: Path, *, malformed: bool = False) -> None:
    now = datetime.now(timezone.utc).isoformat()
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    connection.execute(
        "INSERT INTO category_sources(source_id,content_type,site,service,floor,collection_mode) "
        "VALUES(1,'ebook_comic','FANZA','ebook','comic','COLLECTION_ONLY')"
    )
    connection.execute(
        "INSERT INTO category_collection_runs(run_id,source_id,started_at,finished_at,status,source_sort,requested_hits,fetched_items,response_sha256) "
        "VALUES('run-1',1,?,?,'success','date',1,1,?)",
        (now, now, "0" * 64),
    )
    contributors = '{"author":[{"id":"1"}]}' if malformed else '{"author":[{"id":"1","name":"Fixture"}]}'
    connection.execute(
        "INSERT INTO category_items(item_id,source_id,content_id,title,release_date_raw,item_url,image_json,contributors_json,series_json,genre_json,source_extension_json,first_observed_at,last_observed_at,normalizer_version) "
        "VALUES(1,1,'fixture','Title','2026-01-01','https://example.invalid/item',?,?,?,?,?,?,?,'0.1')",
        (
            '{"large":"https://example.invalid/image.jpg"}',
            contributors,
            '[{"id":"2","name":"Series"}]',
            '[{"id":"3","name":"Genre"}]',
            '{}',
            now,
            now,
        ),
    )
    connection.execute(
        "INSERT INTO category_item_snapshots(item_id,run_id,observed_at,current_price_min,source_sort,source_position,sanitized_raw_json) "
        "VALUES(1,'run-1',?,100,'date',1,'{}')",
        (now,),
    )
    connection.commit()
    connection.close()


class EbookComicStructureAuditTests(unittest.TestCase):
    def test_reports_aggregate_roles_without_entity_values(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "category.db"
            build_database(database)
            with mock.patch.object(
                subject.health,
                "assess",
                return_value=mock.Mock(status=health.HEALTHY),
            ):
                result = subject.assess(database, CONFIG)
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.item_count, 1)
        self.assertEqual(result.contributor_roles[0].role, "author")
        self.assertEqual(result.contributor_roles[0].complete_entry_count, 1)
        self.assertEqual(result.malformed_json_item_count, 0)
        self.assertNotIn("Fixture", str(result.to_dict()))
        self.assertFalse(result.entity_semantics_confirmed)
        self.assertFalse(result.publication_allowed)

    def test_malformed_entity_is_counted_not_exposed(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "category.db"
            build_database(database, malformed=True)
            with mock.patch.object(
                subject.health,
                "assess",
                return_value=mock.Mock(status=health.HEALTHY),
            ):
                result = subject.assess(database, CONFIG)
        self.assertEqual(result.malformed_json_item_count, 1)
        self.assertEqual(result.contributor_roles[0].malformed_entry_count, 1)
        self.assertIn("STRUCTURE_GAPS_PRESENT", result.reason_codes)

    def test_unhealthy_collection_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(
                subject.health,
                "assess",
                return_value=mock.Mock(status=health.FAIL_CLOSED),
            ):
                result = subject.assess(Path(directory) / "missing.db", CONFIG)
        self.assertEqual(result.status, subject.FAIL_CLOSED)
        self.assertFalse(result.publication_allowed)


if __name__ == "__main__":
    unittest.main()
