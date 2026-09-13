from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import category_collection_health as health  # noqa: E402


CONFIG = ROOT / "config" / "category-collection-v0.1.json"
NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


def database(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript((ROOT / "db" / "category-collection-schema.sql").read_text())
    targets = __import__("json").loads(CONFIG.read_text())["targets"]
    for index, target in enumerate(targets, 1):
        connection.execute(
            "INSERT INTO category_sources(source_id,content_type,site,service,floor,collection_mode) VALUES(?,?,?,?,?,'COLLECTION_ONLY')",
            (index, target["content_type"], target["site"], target["service"], target["floor"]),
        )
        run_id = f"run-{index}"
        connection.execute(
            "INSERT INTO category_collection_runs(run_id,source_id,started_at,finished_at,status,source_sort,requested_hits,fetched_items,response_sha256) VALUES(?,?,?,?,'success','date',1,1,?)",
            (run_id, index, "2026-09-12T11:00:00Z", "2026-09-12T11:01:00Z", "a" * 64),
        )
        connection.execute(
            "INSERT INTO category_items(item_id,source_id,content_id,contributors_json,series_json,genre_json,source_extension_json,first_observed_at,last_observed_at,normalizer_version) VALUES(?,?,?,'{}','[]','[]','{}',?,?,?)",
            (index, index, f"item-{index}", "2026-09-12T11:01:00Z", "2026-09-12T11:01:00Z", "0.1"),
        )
        connection.execute(
            "INSERT INTO category_item_snapshots(item_id,run_id,observed_at,source_sort,source_position,sanitized_raw_json) VALUES(?,?,?,'date',1,'{}')",
            (index, run_id, "2026-09-12T11:01:00Z"),
        )
    connection.commit()
    connection.close()


class CategoryCollectionHealthTests(unittest.TestCase):
    def test_healthy_database_is_sanitized_and_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "category.db"
            database(path)
            before = path.read_bytes()
            result = health.assess(path, CONFIG, evaluated_at=NOW)
            after = path.read_bytes()
        self.assertEqual(health.HEALTHY, result.status)
        self.assertEqual(10, result.source_count)
        self.assertEqual(10, result.item_count)
        self.assertTrue(result.publication_closed)
        self.assertEqual(0, result.sensitive_raw_key_count)
        self.assertFalse(result.database_write_performed)
        self.assertFalse(result.publication_allowed)
        self.assertEqual(before, after)

    def test_stale_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "category.db"
            database(path)
            result = health.assess(
                path, CONFIG,
                evaluated_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
            )
        self.assertEqual(health.FAIL_CLOSED, result.status)
        self.assertIn("SOURCE_STALE", result.reason_codes)

    def test_failed_or_running_run_fails_closed(self):
        for status, reason in (("failed", "FAILED_RUN_PRESENT"), ("running", "RUN_INCOMPLETE")):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "category.db"
                database(path)
                connection = sqlite3.connect(path)
                if status == "failed":
                    connection.execute(
                        "INSERT INTO category_collection_runs VALUES('bad',1,?,?,?,'date',1,NULL,NULL,NULL,'COLLECTION_FAILED',0)",
                        ("2026-09-12T11:02:00Z", "2026-09-12T11:03:00Z", status),
                    )
                else:
                    connection.execute(
                        "INSERT INTO category_collection_runs(run_id,source_id,started_at,status,source_sort,requested_hits) VALUES('bad',1,?,'running','date',1)",
                        ("2026-09-12T11:02:00Z",),
                    )
                connection.commit(); connection.close()
                result = health.assess(path, CONFIG, evaluated_at=NOW)
            self.assertEqual(health.FAIL_CLOSED, result.status)
            self.assertIn(reason, result.reason_codes)

    def test_old_failure_is_recovered_by_new_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "category.db"
            database(path)
            connection = sqlite3.connect(path)
            connection.execute(
                "INSERT INTO category_collection_runs VALUES('old-failure',1,?,?,?,'date',1,NULL,NULL,NULL,'COLLECTION_FAILED',0)",
                ("2026-09-12T10:00:00Z", "2026-09-12T10:01:00Z", "failed"),
            )
            connection.commit(); connection.close()
            result = health.assess(path, CONFIG, evaluated_at=NOW)
        self.assertEqual(health.HEALTHY, result.status)
        self.assertEqual(0, result.latest_failed_source_count)

    def test_missing_database_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            result = health.assess(Path(directory) / "missing.db", CONFIG, evaluated_at=NOW)
        self.assertEqual(health.FAIL_CLOSED, result.status)
        self.assertEqual(("HEALTH_CHECK_ERROR",), result.reason_codes)

    def test_sensitive_raw_key_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "category.db"
            database(path)
            connection = sqlite3.connect(path)
            connection.execute(
                "UPDATE category_item_snapshots SET sanitized_raw_json=? WHERE snapshot_id=1",
                ('{"nested":{"Affiliate_URL_SP":"private"}}',),
            )
            connection.commit(); connection.close()
            result = health.assess(path, CONFIG, evaluated_at=NOW)
        self.assertEqual(health.FAIL_CLOSED, result.status)
        self.assertEqual(1, result.sensitive_raw_key_count)
        self.assertIn("SENSITIVE_RAW_KEY_PRESENT", result.reason_codes)


if __name__ == "__main__":
    unittest.main()
