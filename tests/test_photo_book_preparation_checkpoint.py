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
import photo_book_preparation_checkpoint as subject  # noqa: E402


SCHEMA = ROOT / "db" / "category-collection-schema.sql"
CONFIG = ROOT / "config" / "category-collection-v0.1.json"


def build_database(path: Path, *, unsafe_host: bool = False) -> None:
    now = datetime.now(timezone.utc).isoformat()
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))
    connection.execute(
        "INSERT INTO category_sources(source_id,content_type,site,service,floor,collection_mode) "
        "VALUES(1,'photo_book','DMM.com','ebook','photo','COLLECTION_ONLY')"
    )
    item_url = "https://example.invalid/item" if unsafe_host else "https://book.dmm.com/item"
    connection.execute(
        "INSERT INTO category_items(item_id,source_id,content_id,title,release_date_raw,item_url,image_json,contributors_json,series_json,genre_json,source_extension_json,first_observed_at,last_observed_at,normalizer_version) "
        "VALUES(1,1,'fixture','Title','2026-01-01 00:00:00',?,'{}','{}','[]','[]','{}',?,?,'0.1')",
        (item_url, now, now),
    )
    connection.commit()
    connection.close()


class PhotoBookPreparationCheckpointTests(unittest.TestCase):
    def test_boundary_and_synthetic_rehearsal_complete_without_image_read(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "category.db"
            build_database(database)
            with mock.patch.object(
                subject.health, "assess", return_value=mock.Mock(status=health.HEALTHY)
            ):
                result = subject.assess(database, CONFIG)
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.item_count, 1)
        self.assertEqual(result.unique_public_id_count, 1)
        self.assertEqual(result.public_id_collision_count, 0)
        self.assertEqual(result.synthetic_scenario_count, 2)
        self.assertEqual(result.synthetic_scenario_pass_count, 2)
        self.assertTrue(result.synthetic_forbidden_host_blocked)
        self.assertTrue(result.synthetic_forbidden_image_blocked)
        self.assertFalse(result.image_data_read)
        self.assertFalse(result.artifact_created)
        self.assertFalse(result.database_write_performed)
        self.assertFalse(result.external_io_performed)
        self.assertFalse(result.publication_allowed)

    def test_unexpected_product_host_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "category.db"
            build_database(database, unsafe_host=True)
            with mock.patch.object(
                subject.health, "assess", return_value=mock.Mock(status=health.HEALTHY)
            ):
                result = subject.assess(database, CONFIG)
        self.assertEqual(result.status, subject.FAIL_CLOSED)
        self.assertEqual(result.product_url_boundary_valid_count, 0)

    def test_invalid_dates_credentials_and_images_are_rejected(self):
        self.assertFalse(subject._release_datetime("2026-02-30 00:00:00"))
        self.assertFalse(subject._release_datetime("2026-01-01"))
        self.assertFalse(subject._https_product_url("https://user:pass@book.dmm.com/item"))
        _, _, host_blocked, image_blocked = subject._run_synthetic_rehearsal()
        self.assertTrue(host_blocked)
        self.assertTrue(image_blocked)

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
