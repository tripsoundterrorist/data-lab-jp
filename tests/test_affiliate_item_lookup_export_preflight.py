from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_item_lookup_export_preflight as gate  # noqa: E402


class AffiliateItemLookupExportPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.database = self.root / "source.db"

    def create_database(self, rows=None):
        if rows is None:
            rows = [
                ("FANZA", "digital", "videoa", "content-001"),
                ("FANZA", "digital", "videoa", "content-002"),
            ]
        connection = sqlite3.connect(self.database)
        connection.executescript((ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO collection_runs "
            "(collection_run_id, run_type, started_at, first_observed_at, last_observed_at, "
            "site, service, floor, source_sort, hits, max_items, max_pages, status) "
            "VALUES ('run-1', 'native', '2026-09-01T00:00:00Z', "
            "'2026-09-01T00:00:00Z', '2026-09-01T00:00:00Z', "
            "'FANZA', 'digital', 'videoa', 'date', 100, 100, 1, 'running')"
        )
        for index, (site, service, floor, content_id) in enumerate(rows, 1):
            connection.execute(
                "INSERT INTO items "
                "(site, service, floor, content_id, title, first_observed_at, "
                "last_observed_at, master_updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (site, service, floor, content_id, f"Fixture {index}")
                + ("2026-09-01T00:00:00Z",) * 3,
            )
            connection.execute(
                "INSERT INTO item_snapshots "
                "(item_id, collection_run_id, observed_at, source_sort, source_offset, "
                "source_position, query_context_json) VALUES (?, 'run-1', "
                "'2026-09-01T00:00:00Z', 'date', 1, ?, '{}')",
                (index, index),
            )
        connection.commit()
        connection.close()

    def digest(self):
        return sha256(self.database.read_bytes()).hexdigest()

    def test_complete_source_is_review_ready_without_export(self):
        self.create_database()
        before = self.database.read_bytes()
        result = gate.evaluate(self.database, self.digest())
        self.assertEqual(result.status, gate.READY)
        self.assertTrue(result.database_identity_verified)
        self.assertTrue(result.source_query_only)
        self.assertEqual(result.item_count, 2)
        self.assertEqual(result.supported_item_count, 2)
        self.assertTrue(result.scope_exact)
        self.assertTrue(result.identifiers_valid)
        self.assertTrue(result.identifiers_unique)
        self.assertFalse(result.export_performed)
        self.assertFalse(result.publication_allowed)
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(list(self.root.glob("*.sql")), [])

    def test_identity_mismatch_blocks_before_export(self):
        self.create_database()
        result = gate.evaluate(self.database, "0" * 64)
        self.assertEqual(result.status, gate.BLOCKED)
        self.assertFalse(result.database_identity_verified)
        self.assertIn("DATABASE_IDENTITY_MISMATCH", result.reason_codes)
        self.assertFalse(result.export_performed)

    def test_unsupported_or_invalid_source_fails_closed(self):
        cases = (
            (("DMM.com", "digital", "videoa", "content-001"), "SOURCE_SCOPE_UNSUPPORTED"),
            (("FANZA", "digital", "videoa", "bad/content"), "SOURCE_CONTENT_ID_INVALID"),
        )
        for index, (row, reason) in enumerate(cases):
            with self.subTest(reason=reason):
                self.database = self.root / f"case-{index}.db"
                self.create_database([row])
                result = gate.evaluate(self.database, self.digest())
                self.assertEqual(result.status, gate.BLOCKED)
                self.assertIn(reason, result.reason_codes)
                self.assertFalse(result.export_performed)

    def test_safe_result_omits_path_digest_and_identifiers(self):
        self.create_database()
        digest = self.digest()
        result = gate.evaluate(self.database, digest)
        encoded = json.dumps(result.to_dict(), sort_keys=True)
        self.assertNotIn(str(self.database), encoded)
        self.assertNotIn(digest, encoded)
        self.assertNotIn("content-001", encoded)
        self.assertNotIn("itm_", encoded)

    def test_cli_is_machine_readable_and_non_exporting(self):
        self.create_database()
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "affiliate_item_lookup_export_preflight.py"),
                "--db",
                str(self.database),
                "--expected-sha256",
                self.digest(),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], gate.READY)
        self.assertFalse(output["export_performed"])
        self.assertFalse(output["publication_allowed"])


if __name__ == "__main__":
    unittest.main()
