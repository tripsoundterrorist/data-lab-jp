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
import ebook_comic_preparation_checkpoint as subject  # noqa: E402


SCHEMA = ROOT / "db" / "category-collection-schema.sql"
CONFIG = ROOT / "config" / "category-collection-v0.1.json"


def build_database(path: Path, *, unsafe_product_host: bool = False) -> None:
    now = datetime.now(timezone.utc).isoformat()
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    connection.execute(
        "INSERT INTO category_sources(source_id,content_type,site,service,floor,collection_mode) "
        "VALUES(1,'ebook_comic','FANZA','ebook','comic','COLLECTION_ONLY')"
    )
    connection.execute(
        "INSERT INTO category_items(item_id,source_id,content_id,title,release_date_raw,item_url,image_json,contributors_json,series_json,genre_json,source_extension_json,first_observed_at,last_observed_at,normalizer_version) "
        "VALUES(1,1,'fixture','Title','2026-01-01 00:00:00',?,?, '{}','[]','[]','{}',?,?,'0.1')",
        (
            "https://example.invalid/item"
            if unsafe_product_host
            else f"https://{subject.PRODUCT_HOST}/item",
            f'{{"large":"https://{subject.IMAGE_HOST}/image.jpg"}}',
            now,
            now,
        ),
    )
    connection.commit()
    connection.close()


class EbookComicPreparationCheckpointTests(unittest.TestCase):
    def test_boundary_audit_and_synthetic_rehearsal_complete_without_writes(self):
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
        self.assertEqual(result.product_url_boundary_valid_count, 1)
        self.assertEqual(result.image_url_boundary_valid_count, 1)
        self.assertEqual(result.release_datetime_valid_count, 1)
        self.assertEqual(result.unique_public_id_count, 1)
        self.assertEqual(result.public_id_collision_count, 0)
        self.assertEqual(
            result.synthetic_scenario_pass_count,
            result.synthetic_scenario_count,
        )
        self.assertTrue(result.synthetic_forbidden_input_blocked)
        self.assertFalse(result.artifact_created)
        self.assertFalse(result.database_write_performed)
        self.assertFalse(result.external_io_performed)
        self.assertFalse(result.publication_allowed)

    def test_unexpected_product_host_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "category.db"
            build_database(database, unsafe_product_host=True)
            with mock.patch.object(
                subject.health,
                "assess",
                return_value=mock.Mock(status=health.HEALTHY),
            ):
                result = subject.assess(database, CONFIG)
        self.assertEqual(result.status, subject.FAIL_CLOSED)
        self.assertEqual(result.product_url_boundary_valid_count, 0)
        self.assertFalse(result.publication_allowed)

    def test_invalid_dates_and_credentials_are_rejected(self):
        self.assertFalse(subject._release_datetime("2026-02-30 00:00:00"))
        self.assertFalse(subject._release_datetime("2026-01-01"))
        self.assertFalse(
            subject._https_host(
                f"https://user:pass@{subject.PRODUCT_HOST}/item",
                subject.PRODUCT_HOST,
            )
        )

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
