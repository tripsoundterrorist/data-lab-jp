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


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gate = load("snapshot_title_gate", "apply-snapshot-title-migration.py")
copy_migration = load("snapshot_title_copy_migration", "migrate-add-snapshot-titles.py")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_current_database(path: Path, *, running: bool = False) -> None:
    schema = SCHEMA.read_text(encoding="utf-8").split(
        "CREATE TABLE item_snapshot_titles (", 1
    )[0]
    connection = sqlite3.connect(path)
    try:
        connection.executescript(schema)
        status = "running" if running else "unknown"
        run_type = "native" if running else "legacy_migrated"
        finished = None if running else "2026-09-22T00:00:01Z"
        connection.execute(
            """INSERT INTO collection_runs
            (collection_run_id, run_type, started_at, finished_at, site, service,
             floor, source_sort, hits, max_items, max_pages, status)
            VALUES ('run-1', ?, '2026-09-22T00:00:00Z', ?, 'FANZA',
            'digital', 'videoa', 'date', 1, 1, 1, ?)""",
            (run_type, finished, status),
        )
        connection.execute(
            """INSERT INTO items
            (id, site, service, floor, content_id, title, first_observed_at,
             last_observed_at, master_updated_at)
            VALUES (1, 'FANZA', 'digital', 'videoa', 'fixture-1', 'Fixture', ?, ?, ?)""",
            ("2026-09-22T00:00:00Z",) * 3,
        )
        connection.execute(
            """INSERT INTO item_snapshots
            (id, item_id, collection_run_id, observed_at, source_sort,
             source_offset, source_position, price_min, query_context_json)
            VALUES (1, 1, 'run-1', '2026-09-22T00:00:00Z', 'date', 1, 1, 1000, '{}')"""
        )
        connection.execute(
            """INSERT INTO item_lifecycle_observations
            (snapshot_id, contract_version, verification_mode, observation,
             observed_at, expected_content_id_match, affiliate_link_observed,
             source_status_code, inventory_signal, reason_code, created_at)
            VALUES (1, '0.1', 'COLLECTION_PAGE_ITEM', 'API_ITEM_VISIBLE', ?, 1,
            1, 200, 'UNKNOWN', 'AFFILIATE_URL_VALIDATED', ?)""",
            ("2026-09-22T00:00:00Z",) * 2,
        )
        connection.commit()
    finally:
        connection.close()


class SnapshotTitleMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.database = self.root / "data-lab.db"
        self.backups = self.root / "backups"
        self.backups.mkdir()
        create_current_database(self.database)

    def test_preflight_is_read_only_and_apply_creates_verified_backup(self):
        expected = sha256(self.database)
        result = gate.preflight(self.database, expected, self.backups)
        self.assertEqual(result["snapshot_titles"], 0)
        self.assertFalse(list(self.backups.iterdir()))
        applied = gate.apply(self.database, expected, self.backups)
        self.assertEqual(applied["lifecycle_observations"], 1)
        self.assertEqual(len(list(self.backups.glob("data-lab-*.db"))), 1)
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM item_snapshot_titles"
            ).fetchone()[0], 0)
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone(), ("ok",))

    def test_hash_sidecar_active_run_and_existing_table_fail_closed(self):
        with self.assertRaisesRegex(gate.MigrationGateFailure, "EXPECTED_HASH_INVALID"):
            gate.preflight(self.database, "bad", self.backups)
        with self.assertRaisesRegex(gate.MigrationGateFailure, "PRE_MIGRATION_HASH_MISMATCH"):
            gate.preflight(self.database, "0" * 64, self.backups)
        sidecar = Path(f"{self.database}-wal")
        sidecar.write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(gate.MigrationGateFailure, "SQLITE_SIDECAR_PRESENT"):
            gate.preflight(self.database, sha256(self.database), self.backups)
        sidecar.unlink()
        active = self.root / "active.db"
        create_current_database(active, running=True)
        with self.assertRaisesRegex(gate.MigrationGateFailure, "ACTIVE_NATIVE_RUN"):
            gate.preflight(active, sha256(active), self.backups)
        gate.apply(self.database, sha256(self.database), self.backups)
        with self.assertRaisesRegex(gate.MigrationGateFailure, "TARGET_TABLE_ALREADY_EXISTS"):
            gate.preflight(self.database, sha256(self.database), self.backups)

    def test_backup_failure_and_schema_failure_are_fail_closed(self):
        expected = sha256(self.database)
        with mock.patch.object(
            gate.backup, "perform_backup", side_effect=gate.backup.BackupFailure(6, "x")
        ):
            with self.assertRaisesRegex(gate.MigrationGateFailure, "BACKUP_CREATION_FAILED"):
                gate.apply(self.database, expected, self.backups)
        with mock.patch.object(
            gate, "_create_table_sql", side_effect=gate.MigrationGateFailure("TEST_FAILURE")
        ):
            with self.assertRaisesRegex(gate.MigrationGateFailure, "TEST_FAILURE"):
                gate.apply(self.database, expected, self.backups)
        connection = sqlite3.connect(self.database)
        try:
            self.assertIsNone(connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='item_snapshot_titles'"
            ).fetchone())
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM item_lifecycle_observations"
            ).fetchone()[0], 1)
        finally:
            connection.close()

    def test_copy_migration_is_empty_and_requires_current_schema(self):
        result = copy_migration.migrate(self.database)
        self.assertEqual(result["snapshot_titles_created"], 0)
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM item_snapshot_titles"
            ).fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM items").fetchone()[0], 1)
        missing = self.root / "missing.db"
        sqlite3.connect(missing).close()
        with self.assertRaisesRegex(copy_migration.MigrationFailure, "REQUIRED_SCHEMA_MISSING"):
            copy_migration.migrate(missing)


if __name__ == "__main__":
    unittest.main()
