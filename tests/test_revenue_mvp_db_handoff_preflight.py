from hashlib import sha256
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_db_handoff_preflight as gate  # noqa: E402


class DatabaseHandoffPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "handoff.db"

    def create_db(self):
        connection = sqlite3.connect(self.db)
        try:
            connection.executescript((ROOT / "db/schema.sql").read_text())
            connection.execute("INSERT INTO collection_runs (collection_run_id,run_type,started_at,first_observed_at,last_observed_at,site,service,floor,source_sort,hits,max_items,max_pages,status) VALUES ('r','native','2026-09-01T00:00:00Z','2026-09-01T00:00:00Z','2026-09-01T00:00:00Z','FANZA','digital','videoa','date',1,1,1,'running')")
            connection.execute("INSERT INTO items (site,service,floor,content_id,title,first_observed_at,last_observed_at,master_updated_at) VALUES ('FANZA','digital','videoa','c','Fixture','2026-09-01T00:00:00Z','2026-09-01T00:00:00Z','2026-09-01T00:00:00Z')")
            connection.execute("INSERT INTO item_snapshots (item_id,collection_run_id,observed_at,source_sort,source_offset,source_position,query_context_json) VALUES (1,'r','2026-09-01T00:00:00Z','date',1,1,'{}')")
            connection.commit()
        finally:
            connection.close()

    def digest(self):
        return sha256(self.db.read_bytes()).hexdigest()

    def test_matching_identity_and_healthy_db_is_ready(self):
        self.create_db()
        result = gate.preflight(self.db, self.digest())
        self.assertEqual(result.status, gate.READY)
        self.assertTrue(result.identity_verified)
        self.assertTrue(result.read_only)

    def test_mismatch_blocks_without_returning_digest_or_path(self):
        self.create_db()
        result = gate.preflight(self.db, "0" * 64)
        self.assertEqual(result.status, gate.BLOCKED)
        self.assertIn("DATABASE_IDENTITY_MISMATCH", result.reason_codes)
        self.assertNotIn(str(self.db), str(result.to_dict()))
        self.assertNotIn(self.digest(), str(result.to_dict()))

    def test_missing_expected_digest_blocks(self):
        self.create_db()
        self.assertIn("EXPECTED_SHA256_REQUIRED", gate.preflight(self.db, "").reason_codes)

    def test_missing_database_blocks(self):
        result = gate.preflight(self.db, "0" * 64)
        self.assertEqual(result.status, gate.BLOCKED)
        self.assertFalse(result.database_present)

    def test_symlink_is_rejected(self):
        self.create_db()
        link = Path(self.temp.name) / "link.db"
        link.symlink_to(self.db)
        self.assertIn("UNSAFE_DATABASE_ENTRY", gate.preflight(link, self.digest()).reason_codes)

    def test_preflight_does_not_modify_database(self):
        self.create_db()
        before = self.db.read_bytes()
        gate.preflight(self.db, self.digest())
        self.assertEqual(self.db.read_bytes(), before)
