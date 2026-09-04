from hashlib import sha256
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import revenue_mvp_db_audit as audit  # noqa: E402


class RevenueMvpDatabaseAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.db = Path(self.temporary.name) / "audit.db"

    def create_database(self, populated=True):
        schema = (ROOT / "db/schema.sql").read_text(encoding="utf-8")
        connection = sqlite3.connect(self.db)
        try:
            connection.executescript(schema)
            if populated:
                connection.execute(
                    "INSERT INTO collection_runs "
                    "(collection_run_id, run_type, started_at, first_observed_at, "
                    "last_observed_at, site, service, floor, source_sort, hits, "
                    "max_items, max_pages, status) VALUES "
                    "('run-1', 'native', '2026-09-01T00:00:00Z', "
                    "'2026-09-01T00:00:00Z', '2026-09-02T00:00:00Z', "
                    "'FANZA', 'digital', 'videoa', 'date', 100, 100, 1, 'running')"
                )
                connection.execute(
                    "INSERT INTO items "
                    "(site, service, floor, content_id, title, first_observed_at, "
                    "last_observed_at, master_updated_at) VALUES "
                    "('FANZA', 'digital', 'videoa', 'cid-1', 'Fixture', "
                    "'2026-09-01T00:00:00Z', '2026-09-02T00:00:00Z', "
                    "'2026-09-02T00:00:00Z')"
                )
                for position, observed in enumerate(
                    ("2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z"), 1
                ):
                    connection.execute(
                        "INSERT INTO item_snapshots "
                        "(item_id, collection_run_id, observed_at, source_sort, "
                        "source_offset, source_position, query_context_json) "
                        "VALUES (1, 'run-1', ?, 'date', 1, ?, '{}')",
                        (observed, position),
                    )
            connection.commit()
        finally:
            connection.close()

    def test_valid_database_returns_required_baseline(self):
        self.create_database()
        result = audit.audit_database(self.db)
        self.assertEqual(result.status, audit.READY)
        self.assertEqual(result.items_count, 1)
        self.assertEqual(result.item_snapshots_count, 2)
        self.assertEqual(result.collection_runs_count, 1)
        self.assertEqual(result.average_observations_per_item, 2.0)
        self.assertEqual(result.oldest_observed_at, "2026-09-01T00:00:00Z")
        self.assertEqual(result.latest_observed_at, "2026-09-02T00:00:00Z")
        self.assertEqual(result.integrity_check, "ok")
        self.assertEqual(result.foreign_key_violation_count, 0)
        self.assertTrue(result.read_only)
        self.assertFalse(result.publication_allowed)

    def test_audit_does_not_modify_database(self):
        self.create_database()
        before = sha256(self.db.read_bytes()).hexdigest()
        audit.audit_database(self.db)
        after = sha256(self.db.read_bytes()).hexdigest()
        self.assertEqual(after, before)

    def test_missing_database_is_blocked_without_path_echo(self):
        missing = Path(self.temporary.name) / "secret-name.db"
        result = audit.audit_database(missing)
        self.assertEqual(result.status, audit.BLOCKED)
        self.assertEqual(result.reason_codes, ("DATABASE_MISSING",))
        self.assertNotIn(str(missing), str(result.to_dict()))

    def test_missing_schema_is_blocked(self):
        sqlite3.connect(self.db).close()
        result = audit.audit_database(self.db)
        self.assertEqual(result.status, audit.BLOCKED)
        self.assertEqual(result.reason_codes, ("REQUIRED_SCHEMA_MISSING",))

    def test_empty_database_is_blocked(self):
        self.create_database(populated=False)
        result = audit.audit_database(self.db)
        self.assertEqual(result.status, audit.BLOCKED)
        self.assertIn("NO_ITEMS", result.reason_codes)
        self.assertIn("NO_SNAPSHOTS", result.reason_codes)
        self.assertIn("NO_COLLECTION_RUNS", result.reason_codes)
        self.assertIn("OBSERVATION_RANGE_UNAVAILABLE", result.reason_codes)

    def test_cli_missing_default_fails_closed(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/revenue_mvp_db_audit.py"),
             "--db", str(Path(self.temporary.name) / "missing.db")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn('"status": "BLOCKED"', result.stdout)
        self.assertNotIn(self.temporary.name, result.stdout)


if __name__ == "__main__":
    unittest.main()
