import hashlib
import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "db" / "schema.sql"
SPEC = importlib.util.spec_from_file_location("production_lifecycle_migration", ROOT / "scripts" / "apply-lifecycle-observation-migration.py")
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_legacy_database(path: Path, *, running: bool = False) -> None:
    old_schema = SCHEMA.read_text(encoding="utf-8").split("CREATE TABLE item_lifecycle_observations (", 1)[0]
    connection = sqlite3.connect(path)
    try:
        connection.executescript(old_schema)
        if running:
            connection.execute(
                """INSERT INTO collection_runs (collection_run_id, run_type, started_at,
                site, service, floor, source_sort, hits, max_items, max_pages, status)
                VALUES ('run-1', 'native', '2026-09-21T00:00:00Z', 'FANZA', 'digital',
                'videoa', 'date', 1, 1, 1, 'running')"""
            )
        else:
            connection.execute(
                "INSERT INTO collection_runs (collection_run_id, run_type, status) VALUES ('run-1', 'legacy_migrated', 'unknown')"
            )
        connection.execute(
            """INSERT INTO items (id, site, service, floor, content_id, first_observed_at,
            last_observed_at, master_updated_at) VALUES (1, 'FANZA', 'digital', 'videoa',
            'fixture-1', ?, ?, ?)""", ("2026-09-21T00:00:00Z",) * 3,
        )
        connection.execute(
            """INSERT INTO item_snapshots (id, item_id, collection_run_id, observed_at,
            source_sort, source_offset, source_position, query_context_json)
            VALUES (1, 1, 'run-1', ?, 'date', 1, 1, '{}')""", ("2026-09-21T00:00:00Z",),
        )
        connection.commit()
    finally:
        connection.close()


class ProductionLifecycleMigrationGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.database = self.root / "data-lab.db"
        self.backups = self.root / "backups"
        self.backups.mkdir()
        create_legacy_database(self.database)

    def test_apply_creates_verified_backup_and_empty_additive_table(self):
        result = runner.apply(self.database, sha256(self.database), self.backups)
        self.assertEqual(result["lifecycle_observations"], 0)
        self.assertEqual(result["items"], 1)
        self.assertEqual(len(list(self.backups.glob("data-lab-*.db"))), 1)
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM item_lifecycle_observations").fetchone()[0], 0)
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone(), ("ok",))

    def test_hash_mismatch_fails_before_backup_or_write(self):
        with self.assertRaisesRegex(runner.MigrationGateFailure, "PRE_MIGRATION_HASH_MISMATCH"):
            runner.apply(self.database, "0" * 64, self.backups)
        self.assertFalse(list(self.backups.iterdir()))

    def test_malformed_expected_hash_fails_closed_before_backup_or_write(self):
        with self.assertRaisesRegex(runner.MigrationGateFailure, "EXPECTED_HASH_INVALID"):
            runner.apply(self.database, "not-a-sha256", self.backups)
        self.assertFalse(list(self.backups.iterdir()))

    def test_active_run_and_sidecar_fail_closed(self):
        active = self.root / "active.db"
        create_legacy_database(active, running=True)
        with self.assertRaisesRegex(runner.MigrationGateFailure, "ACTIVE_NATIVE_RUN"):
            runner.preflight(active, sha256(active), self.backups)
        Path(f"{self.database}-wal").write_text("present", encoding="utf-8")
        with self.assertRaisesRegex(runner.MigrationGateFailure, "SQLITE_SIDECAR_PRESENT"):
            runner.preflight(self.database, sha256(self.database), self.backups)

    def test_backup_failure_and_already_migrated_fail_closed(self):
        with mock.patch.object(runner.backup, "perform_backup", side_effect=runner.backup.BackupFailure(6, "x")):
            with self.assertRaisesRegex(runner.MigrationGateFailure, "BACKUP_CREATION_FAILED"):
                runner.apply(self.database, sha256(self.database), self.backups)
        runner.apply(self.database, sha256(self.database), self.backups)
        with self.assertRaisesRegex(runner.MigrationGateFailure, "TARGET_TABLE_ALREADY_EXISTS"):
            runner.preflight(self.database, sha256(self.database), self.backups)

    def test_schema_failure_rolls_back_without_backfill(self):
        expected = sha256(self.database)
        with mock.patch.object(runner, "_create_schema_objects", side_effect=runner.MigrationGateFailure("TEST_FAILURE")):
            with self.assertRaisesRegex(runner.MigrationGateFailure, "TEST_FAILURE"):
                runner.apply(self.database, expected, self.backups)
        with sqlite3.connect(self.database) as connection:
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'item_lifecycle_observations'").fetchone())
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM item_snapshots").fetchone()[0], 1)

    def test_preflight_is_dry_run_without_explicit_apply(self):
        result = runner.preflight(self.database, sha256(self.database), self.backups)
        self.assertEqual(result["lifecycle_observations"], 0)
        self.assertFalse(list(self.backups.iterdir()))
        self.assertEqual(runner.main(["--db", str(self.database), "--expected-sha256", sha256(self.database), "--backup-dir", str(self.backups)]), 0)
        self.assertFalse(list(self.backups.iterdir()))


if __name__ == "__main__":
    unittest.main()
