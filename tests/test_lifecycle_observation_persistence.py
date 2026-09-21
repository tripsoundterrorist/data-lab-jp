import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SCHEMA = ROOT / "db" / "schema.sql"
sys.path.insert(0, str(SCRIPTS))


def load(name, filename):
    specification = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


collector = load("lifecycle_observation_collector", "collect-dmm-items.py")
migration = load(
    "lifecycle_observation_migration",
    "migrate-add-lifecycle-observations.py",
)
STAMP = "2026-09-16T07:00:42Z"
SAFE_URL = "https://al.dmm.co.jp/opaque-test"


class LifecycleObservationPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.addCleanup(self.connection.close)
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(SCHEMA.read_text(encoding="utf-8"))
        self.connection.execute(
            """
            INSERT INTO collection_runs (collection_run_id, run_type, status)
            VALUES ('run-1', 'legacy_migrated', 'unknown')
            """
        )
        self.connection.execute(
            """
            INSERT INTO items (
              id, site, service, floor, content_id, first_observed_at,
              last_observed_at, master_updated_at
            ) VALUES (1, 'FANZA', 'digital', 'videoa', 'fixture-1', ?, ?, ?)
            """,
            (STAMP, STAMP, STAMP),
        )

    def insert_snapshot(self, snapshot_id=1):
        self.connection.execute(
            """
            INSERT INTO item_snapshots (
              id, item_id, collection_run_id, observed_at, source_sort,
              source_offset, source_position, query_context_json
            ) VALUES (?, 1, 'run-1', ?, 'date', 1, ?, '{}')
            """,
            (snapshot_id, STAMP, snapshot_id),
        )

    def test_schema_is_additive_empty_and_contains_no_sensitive_columns(self):
        columns = {
            row[1]
            for row in self.connection.execute(
                "PRAGMA table_info(item_lifecycle_observations)"
            )
        }
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM item_lifecycle_observations"
            ).fetchone()[0],
            0,
        )
        for forbidden in (
            "affiliate_url",
            "affiliateURL",
            "api_id",
            "affiliate_id",
            "content_id",
            "raw_response",
            "query_context_json",
        ):
            self.assertNotIn(forbidden, columns)
        self.assertEqual(collector.run_preflight.__module__, "collector_preflight")
        import collector_preflight

        self.assertEqual(
            collector_preflight.inspect_schema(self.connection),
            (None, None),
        )

    def test_safe_presence_is_stored_without_url_value(self):
        self.insert_snapshot()
        collector.store_sanitized_lifecycle_observation(
            self.connection,
            snapshot_id=1,
            observed_at=STAMP,
            source_status_code=200,
            affiliate_url=SAFE_URL,
        )
        row = self.connection.execute(
            "SELECT * FROM item_lifecycle_observations"
        ).fetchone()
        self.assertEqual(row[6], 1)
        self.assertEqual(row[9], "AFFILIATE_URL_VALIDATED")
        self.assertNotIn(SAFE_URL, json.dumps(row))

    def test_snapshot_title_is_bounded_and_rolls_back_with_lifecycle_observation(self):
        self.insert_snapshot()
        with self.connection:
            collector.store_sanitized_lifecycle_observation(
                self.connection, snapshot_id=1, observed_at=STAMP,
                source_status_code=200, affiliate_url=SAFE_URL,
            )
            collector.store_snapshot_title(
                self.connection, snapshot_id=1, title="fixture title", observed_at=STAMP,
            )
        row = self.connection.execute(
            "SELECT title, observed_at FROM item_snapshot_titles WHERE snapshot_id = 1"
        ).fetchone()
        self.assertEqual(row, ("fixture title", STAMP))
        self.insert_snapshot(2)
        with self.assertRaises(ValueError):
            collector.store_snapshot_title(
                self.connection, snapshot_id=2, title="", observed_at=STAMP,
            )
        self.assertEqual(self.connection.execute(
            "SELECT COUNT(*) FROM item_snapshot_titles"
        ).fetchone()[0], 1)
        with self.assertRaisesRegex(ValueError, "SNAPSHOT_TITLE_PROVENANCE_INVALID"):
            collector.store_snapshot_title(
                self.connection,
                snapshot_id=2,
                title="fixture title",
                observed_at="2026-09-16T07:00:43Z",
            )
        with self.assertRaises(sqlite3.IntegrityError):
            collector.store_snapshot_title(
                self.connection,
                snapshot_id=1,
                title="duplicate",
                observed_at=STAMP,
            )

    def test_absent_and_invalid_urls_store_false_or_unknown(self):
        cases = (
            (None, 0, "AFFILIATE_URL_ABSENT"),
            ("http://al.dmm.co.jp/unsafe", None, "AFFILIATE_URL_VALIDATION_FAILED"),
            ("https://example.invalid/unsafe", None, "AFFILIATE_URL_VALIDATION_FAILED"),
        )
        for index, (value, expected, reason) in enumerate(cases, start=1):
            with self.subTest(reason=reason):
                self.insert_snapshot(index)
                collector.store_sanitized_lifecycle_observation(
                    self.connection,
                    snapshot_id=index,
                    observed_at=STAMP,
                    source_status_code=200,
                    affiliate_url=value,
                )
                row = self.connection.execute(
                    """
                    SELECT affiliate_link_observed, reason_code
                    FROM item_lifecycle_observations WHERE snapshot_id = ?
                    """,
                    (index,),
                ).fetchone()
                self.assertEqual(row, (expected, reason))

    def test_duplicate_and_malformed_observations_fail_closed(self):
        self.insert_snapshot()
        collector.store_sanitized_lifecycle_observation(
            self.connection,
            snapshot_id=1,
            observed_at=STAMP,
            source_status_code=200,
            affiliate_url=SAFE_URL,
        )
        with self.assertRaises(sqlite3.IntegrityError):
            collector.store_sanitized_lifecycle_observation(
                self.connection,
                snapshot_id=1,
                observed_at=STAMP,
                source_status_code=200,
                affiliate_url=SAFE_URL,
            )
        self.insert_snapshot(2)
        with self.assertRaises(sqlite3.IntegrityError):
            collector.store_sanitized_lifecycle_observation(
                self.connection,
                snapshot_id=2,
                observed_at=STAMP,
                source_status_code=201,
                affiliate_url=SAFE_URL,
            )

    def test_snapshot_and_observation_rollback_together(self):
        with self.assertRaises(RuntimeError):
            with self.connection:
                self.insert_snapshot()
                collector.store_sanitized_lifecycle_observation(
                    self.connection,
                    snapshot_id=1,
                    observed_at=STAMP,
                    source_status_code=200,
                    affiliate_url=SAFE_URL,
                )
                collector.store_snapshot_title(
                    self.connection,
                    snapshot_id=1,
                    title="fixture title",
                    observed_at=STAMP,
                )
                raise RuntimeError("rollback")
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM item_snapshots").fetchone()[0],
            0,
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM item_lifecycle_observations"
            ).fetchone()[0],
            0,
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM item_snapshot_titles"
            ).fetchone()[0],
            0,
        )

    def test_copy_migration_creates_empty_table_without_backfill(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "copy.db"
            old_schema = SCHEMA.read_text(encoding="utf-8").split(
                "CREATE TABLE item_lifecycle_observations (", 1
            )[0]
            connection = sqlite3.connect(path)
            connection.executescript(old_schema)
            connection.execute(
                """
                INSERT INTO collection_runs (collection_run_id, run_type, status)
                VALUES ('run-1', 'legacy_migrated', 'unknown')
                """
            )
            connection.execute(
                """
                INSERT INTO items (
                  id, site, service, floor, content_id, first_observed_at,
                  last_observed_at, master_updated_at
                ) VALUES (1, 'FANZA', 'digital', 'videoa', 'fixture-1', ?, ?, ?)
                """,
                (STAMP, STAMP, STAMP),
            )
            connection.execute(
                """
                INSERT INTO item_snapshots (
                  id, item_id, collection_run_id, observed_at, source_sort,
                  source_offset, source_position, query_context_json
                ) VALUES (1, 1, 'run-1', ?, 'date', 1, 1, '{}')
                """,
                (STAMP,),
            )
            connection.commit()
            connection.close()

            result = migration.migrate(path)
            self.assertEqual(result["snapshots_preserved"], 1)
            self.assertEqual(result["lifecycle_observations_created"], 0)
            connection = sqlite3.connect(path)
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM item_lifecycle_observations"
                ).fetchone()[0],
                0,
            )
            connection.close()


if __name__ == "__main__":
    unittest.main()
