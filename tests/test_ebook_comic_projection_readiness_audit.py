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
import ebook_comic_projection_readiness_audit as subject  # noqa: E402


SCHEMA = ROOT / "db" / "category-collection-schema.sql"
CONFIG = ROOT / "config" / "category-collection-v0.1.json"


def build_database(
    path: Path,
    *,
    missing_author: bool = False,
    incomplete_review: bool = False,
) -> None:
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
    contributors = (
        '{"manufacture":[{"id":"2","name":"Source"}]}'
        if missing_author
        else '{"author":[{"id":"1","name":"Author"}],"manufacture":[{"id":"2","name":"Source"}]}'
    )
    connection.execute(
        "INSERT INTO category_items(item_id,source_id,content_id,title,release_date_raw,item_url,image_json,contributors_json,series_json,genre_json,source_extension_json,first_observed_at,last_observed_at,normalizer_version) "
        "VALUES(1,1,'fixture','Title','2026-01-01','https://example.invalid/item',?,?,?,?,?,?,?,'0.1')",
        (
            '{"large":"https://example.invalid/image.jpg"}',
            contributors,
            '[{"id":"3","name":"Series"}]',
            '[{"id":"4","name":"Genre"}]',
            '{}',
            now,
            now,
        ),
    )
    connection.execute(
        "INSERT INTO category_item_snapshots(item_id,run_id,observed_at,current_price_min,review_average,review_count,source_sort,source_position,sanitized_raw_json) "
        "VALUES(1,'run-1',?,100,?,3,'date',1,'{}')",
        (now, None if incomplete_review else 4.0),
    )
    connection.commit()
    connection.close()


class EbookComicProjectionReadinessAuditTests(unittest.TestCase):
    def test_ready_row_is_counted_without_artifact(self):
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
        self.assertEqual(result.structure_ready_count, 1)
        self.assertEqual(result.structure_blocked_count, 0)
        self.assertEqual(result.blocker_reasons, ())
        self.assertFalse(result.artifact_created)
        self.assertFalse(result.database_write_performed)
        self.assertFalse(result.publication_allowed)

    def test_blocked_row_is_aggregate_only(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "category.db"
            build_database(database, missing_author=True)
            with mock.patch.object(
                subject.health,
                "assess",
                return_value=mock.Mock(status=health.HEALTHY),
            ):
                result = subject.assess(database, CONFIG)
        self.assertEqual(result.structure_ready_count, 0)
        self.assertEqual(result.structure_blocked_count, 1)
        self.assertEqual(
            result.blocker_reasons[0].reason_code,
            "PROJECTION_ENTITY_REFERENCE_INVALID",
        )
        self.assertEqual(result.blocker_reasons[0].count, 1)
        self.assertIn("STRUCTURE_BLOCKERS_PRESENT", result.reason_codes)
        rendered = str(result.to_dict())
        self.assertNotIn("fixture", rendered)
        self.assertNotIn("Author", rendered)

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

    def test_incomplete_review_pair_gets_fixed_aggregate_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "category.db"
            build_database(database, incomplete_review=True)
            with mock.patch.object(
                subject.health,
                "assess",
                return_value=mock.Mock(status=health.HEALTHY),
            ):
                result = subject.assess(database, CONFIG)
        self.assertEqual(result.structure_blocked_count, 1)
        self.assertEqual(
            result.blocker_reasons[0].reason_code,
            "PROJECTION_REVIEW_PAIR_INCOMPLETE",
        )
        self.assertEqual(result.blocker_reasons[0].count, 1)


if __name__ == "__main__":
    unittest.main()
