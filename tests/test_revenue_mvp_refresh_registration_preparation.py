"""Synthetic-only registration preparation: no remote client or real DB."""
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_refresh_registration_preparation as subject
from revenue_mvp_lifecycle_receipt import public_item_id

NOW = datetime(2026, 10, 19, 9, tzinfo=timezone.utc)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def page(ids):
    return ''.join(f'<article class="item"><a href="/go/{value}">item</a></article>' for value in ids).encode()


class RegistrationPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "fixture.db"
        self.content = [f"synthetic-{i:03}" for i in range(100)]
        self.ids = [public_item_id("FANZA", "digital", "videoa", value) for value in self.content]
        self.source = page([self.ids[0]] + [f"itm_{i:024x}" for i in range(99)])
        self.candidate = page(self.ids)
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TABLE items(site TEXT,service TEXT,floor TEXT,content_id TEXT)")
            db.executemany("INSERT INTO items VALUES ('FANZA','digital','videoa',?)", [(v,) for v in self.content])
        self.snapshot = ''.join(
            "INSERT INTO affiliate_item_lookup "
            "(public_id,content_id,rights_status,lifecycle_status,verification_status,affiliate_enabled,updated_at) "
            f"VALUES ('{public}','{content}','CONDITIONALLY_APPROVED','RESOLVED','PASS',1,'2026-10-19T08:58:00Z');\n"
            for public, content in zip(self.ids[:3], self.content[:3])
        ).encode()
        self.db_hash = digest(self.db.read_bytes())

    def prepare(self, **options):
        arguments = dict(expected_source_sha256=digest(self.source),
                         expected_candidate_sha256=digest(self.candidate),
                         expected_database_sha256=self.db_hash,
                         expected_snapshot_sha256=digest(self.snapshot),
                         snapshot_observed_at=NOW-timedelta(minutes=1), evaluated_at=NOW,
                         expected_missing_count=97, batch_index=0)
        arguments.update(options)
        return subject.prepare(self.source, self.candidate, self.db, self.snapshot, **arguments)

    def blocked(self, **options):
        receipt, payload = self.prepare(**options)
        self.assertEqual(receipt.status, subject.BLOCKED)
        self.assertIsNone(payload)
        self.assertFalse(receipt.d1_write_performed)
        self.assertFalse(receipt.publication_allowed)
        return receipt

    def test_exact_batch_is_disabled_only_and_does_not_write_files(self):
        before_files = sorted(p.name for p in Path(self.temp.name).iterdir())
        receipt, payload = self.prepare()
        self.assertEqual(receipt.status, subject.READY)
        self.assertEqual((receipt.missing_count, receipt.selected_count, receipt.batch_count), (97, 5, 20))
        self.assertEqual(digest(payload), receipt.sql_sha256)
        self.assertEqual(receipt.candidate_sha256, digest(self.candidate))
        self.assertEqual(receipt.snapshot_sha256, digest(self.snapshot))
        for field in ("publication_allowed", "api_request_performed", "d1_write_performed", "output_written",
                      "authoritative_snapshot_provenance_verified"):
            self.assertFalse(getattr(receipt, field))
        self.assertTrue(receipt.explicit_live_approval_required)
        self.assertTrue(receipt.database_unchanged)
        self.assertEqual(digest(self.db.read_bytes()), self.db_hash)
        self.assertEqual(sorted(p.name for p in Path(self.temp.name).iterdir()), before_files)
        self.assertNotIn(b"\n", payload)
        self.assertEqual(payload.count(b"INSERT INTO"), 1)
        for forbidden in (b"UPDATE", b"DELETE", b"REPLACE", b"IGNORE", b"affiliate_redirect_target"):
            self.assertNotIn(forbidden, payload)

    def test_batches_are_disjoint_complete_and_last_is_two(self):
        all_new = set()
        for index in range(20):
            receipt, payload = self.prepare(batch_index=index)
            self.assertEqual(receipt.status, subject.READY)
            with sqlite3.connect(":memory:") as db:
                db.executescript(subject.preapproval.SCHEMA.read_text(encoding="utf-8"))
                db.executescript(self.snapshot.decode())
                before = db.execute("SELECT * FROM affiliate_item_lookup ORDER BY public_id").fetchall()
                db.execute(payload.decode())
                rows = db.execute("SELECT public_id,affiliate_enabled FROM affiliate_item_lookup").fetchall()
                selected = {public for public, enabled in rows if enabled == 0}
                self.assertFalse(all_new & selected)
                all_new |= selected
                self.assertEqual(len(selected), 2 if index == 19 else 5)
                after = db.execute("SELECT * FROM affiliate_item_lookup WHERE affiliate_enabled=1 ORDER BY public_id").fetchall()
                self.assertEqual(before, after)
                self.assertEqual(db.execute("SELECT count(*) FROM affiliate_redirect_target").fetchone()[0], 0)
        self.assertEqual(len(all_new), 97)
        self.assertNotIn(self.ids[0], all_new)
        self.assertEqual(self.prepare()[1], self.prepare()[1])

    def test_all_hashes_are_required_and_exact(self):
        for key in ("expected_source_sha256", "expected_candidate_sha256",
                    "expected_database_sha256", "expected_snapshot_sha256"):
            for value in (None, "bad", "0"*64):
                with self.subTest(key=key, value=value):
                    self.blocked(**{key:value})

    def test_batch_indices_and_missing_counts_fail_closed(self):
        for index in (-1, True, "0", 20, 100):
            self.blocked(batch_index=index)
        for count in (True, 0, 98, 100, "97"):
            self.blocked(expected_missing_count=count)

    def test_stale_future_and_naive_timestamps_fail_closed(self):
        for stamp in (NOW-timedelta(minutes=15,seconds=1), NOW+timedelta(seconds=1), NOW.replace(tzinfo=None), None):
            self.blocked(snapshot_observed_at=stamp)
        self.blocked(evaluated_at=NOW.replace(tzinfo=None))
        self.assertEqual(self.prepare(snapshot_observed_at=NOW-timedelta(minutes=15))[0].status, subject.READY)

    def test_count_drift_duplicate_and_malformed_routes_block(self):
        for ids in (self.ids[:-1], self.ids+[self.ids[0]], self.ids[:-1]+[self.ids[0]], self.ids[:-1]+["bad"]):
            with self.subTest(ids_count=len(ids)):
                self.candidate = page(ids)
                self.blocked()

    def test_wrong_delta_blocks_instead_of_relaxing_old_guard(self):
        self.source = page(self.ids[:2]+[f"itm_{i:024x}" for i in range(98)])
        self.assertEqual(self.blocked().reason_code, "EXACT_99_DELTA_REQUIRED")

    def test_missing_local_mapping_and_duplicate_local_mapping_block(self):
        with sqlite3.connect(self.db) as db:
            db.execute("DELETE FROM items WHERE content_id=?", (self.content[-1],))
        self.db_hash = digest(self.db.read_bytes())
        self.assertEqual(self.blocked().reason_code, "LOCAL_MAPPING_COVERAGE_INVALID")
        with sqlite3.connect(self.db) as db:
            db.execute("INSERT INTO items VALUES ('FANZA','digital','videoa',?)", (self.content[0],))
        self.db_hash = digest(self.db.read_bytes())
        self.assertEqual(self.blocked().reason_code, "LOCAL_MAPPING_DUPLICATE")

    def test_mapping_conflict_for_either_identifier_blocks(self):
        original = self.snapshot
        self.snapshot = original.replace(self.content[0].encode(), b"conflicting-content")
        self.assertEqual(self.blocked().reason_code, "D1_MAPPING_CONFLICT")
        self.snapshot = original.replace(self.ids[0].encode(), b"itm_"+b"f"*24)
        self.assertEqual(self.blocked().reason_code, "D1_MAPPING_CONFLICT")

    def test_missing_current_public_route_may_not_be_registered_as_new(self):
        self.snapshot = b"\n".join(self.snapshot.splitlines()[1:])
        self.assertEqual(self.blocked(expected_missing_count=98).reason_code, "MISSING_SCOPE_MISMATCH")

    def test_invalid_snapshot_sql_never_yields_sql_output(self):
        for payload in (b"DROP TABLE affiliate_item_lookup;", b"ATTACH DATABASE ':memory:' AS extra;", b"bad sql", b"\xff"):
            self.snapshot = payload
            receipt = self.blocked()
            self.assertNotIn("sql", receipt.reason_code.lower())

    def test_existing_redirects_and_audit_events_are_preserved(self):
        self.snapshot += (
            "INSERT INTO affiliate_redirect_target (public_id,content_id,affiliate_url,verified_at) "
            f"VALUES ('{self.ids[0]}','{self.content[0]}','https://example.invalid/synthetic','2026-10-19T08:58:00Z');"
            "INSERT INTO affiliate_lifecycle_revalidation_event "
            "(public_id,checked_at,outcome,affiliate_enabled_after,reason_code) "
            f"VALUES ('{self.ids[0]}','2026-10-19T08:58:00Z','VALID',1,'SYNTHETIC');"
        ).encode()
        receipt, payload = self.prepare()
        self.assertEqual(receipt.status, subject.READY)
        with sqlite3.connect(":memory:") as db:
            db.executescript(subject.preapproval.SCHEMA.read_text(encoding="utf-8"))
            db.executescript(self.snapshot.decode())
            tables = ("affiliate_redirect_target", "affiliate_lifecycle_revalidation_event")
            before = [db.execute(f"SELECT * FROM {table}").fetchall() for table in tables]
            db.execute(payload.decode())
            self.assertEqual(before, [db.execute(f"SELECT * FROM {table}").fetchall() for table in tables])
            self.assertEqual(db.execute("SELECT count(*) FROM affiliate_runtime_redirect_target").fetchone()[0], 1)

    def test_stale_existing_rows_are_not_inserted_or_reset(self):
        self.snapshot = self.snapshot.replace(b"2026-10-19T08:58:00Z", b"2026-09-01T00:00:00Z")
        receipt, payload = self.prepare()
        self.assertEqual(receipt.status, subject.READY)
        for public in self.ids[:3]:
            self.assertNotIn(public.encode(), payload)

    def test_receipt_does_not_expose_identifiers_or_sql(self):
        receipt, payload = self.prepare()
        text = str(receipt.to_dict())
        for value in self.ids + self.content:
            self.assertNotIn(value, text)
        self.assertNotIn(payload.decode(), text)

    def test_database_sidecars_block(self):
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = Path(str(self.db)+suffix)
            sidecar.touch()
            self.assertEqual(self.blocked().reason_code, "DATABASE_BOUNDARY_INVALID")
            sidecar.unlink()

    def test_mid_read_database_change_blocks(self):
        original = Path.read_bytes
        calls = 0
        def unstable(path):
            nonlocal calls
            value = original(path)
            if path == self.db:
                calls += 1
                if calls > 1:
                    return value+b"changed"
            return value
        with patch.object(Path, "read_bytes", unstable):
            self.assertEqual(self.blocked().reason_code, "DATABASE_CHANGED_DURING_PREPARATION")


if __name__ == "__main__":
    unittest.main()
