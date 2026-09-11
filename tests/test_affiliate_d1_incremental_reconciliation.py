import hashlib
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from affiliate_d1_incremental_reconciliation import (  # noqa: E402
    FAIL_CLOSED,
    READY,
    SYNCHRONIZED,
    reconcile_files,
    reconcile_snapshots,
)


def candidate(rows: list[tuple[str, str]]) -> bytes:
    lines = ["BEGIN TRANSACTION;"]
    lines.extend(
        "INSERT INTO affiliate_item_lookup (public_id, content_id, updated_at) "
        f"VALUES ('{public_id}', '{content_id}', '1970-01-01T00:00:00Z');"
        for public_id, content_id in rows
    )
    lines.append("COMMIT;")
    return ("\n".join(lines) + "\n").encode()


def remote(rows: list[tuple[str, str]], *, enabled: int = 0) -> bytes:
    lines = ["PRAGMA defer_foreign_keys=TRUE;"]
    lines.extend(
        'INSERT INTO "affiliate_item_lookup" '
        '("public_id","content_id","rights_status","lifecycle_status",'
        '"verification_status","affiliate_enabled","updated_at") VALUES'
        f"('{public_id}','{content_id}','PENDING_SEPARATE_POLICY',"
        f"'PENDING_OFFICIAL_CONFIRMATION','PENDING',{enabled},'1970-01-01T00:00:00Z');"
        for public_id, content_id in rows
    )
    return ("\n".join(lines) + "\n").encode()


ROWS = [
    ("itm_aaaaaaaaaaaaaaaaaaaaaaaa", "content-a"),
    ("itm_bbbbbbbbbbbbbbbbbbbbbbbb", "content-b"),
]


class IncrementalReconciliationTests(unittest.TestCase):
    def reconcile(self, remote_bytes: bytes, candidate_bytes: bytes, **overrides):
        arguments = {
            "expected_remote_sha256": hashlib.sha256(remote_bytes).hexdigest(),
            "expected_candidate_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
            "expected_remote_row_count": 1,
            "expected_candidate_row_count": 2,
        }
        arguments.update(overrides)
        return reconcile_snapshots(remote_bytes, candidate_bytes, **arguments)

    def test_exact_subset_builds_insert_only_delta(self):
        result, delta = self.reconcile(remote(ROWS[:1]), candidate(ROWS))
        self.assertEqual(READY, result.status)
        self.assertEqual(1, result.missing_row_count)
        self.assertTrue(result.remote_subset_verified)
        self.assertNotIn(ROWS[0][0].encode(), delta)
        self.assertIn(ROWS[1][0].encode(), delta)
        self.assertNotIn(b"BEGIN TRANSACTION", delta)
        self.assertEqual(1, delta.count(b"INSERT INTO"))

    def test_mapping_mismatch_fails_closed(self):
        changed = [(ROWS[0][0], "changed-content")]
        result, delta = self.reconcile(remote(changed), candidate(ROWS))
        self.assertEqual(FAIL_CLOSED, result.status)
        self.assertIn("REMOTE_MAPPING_NOT_CANDIDATE_SUBSET", result.reason_codes)
        self.assertIsNone(delta)

    def test_equal_inputs_report_already_synchronized(self):
        remote_bytes = remote(ROWS)
        candidate_bytes = candidate(ROWS)
        result, delta = self.reconcile(
            remote_bytes,
            candidate_bytes,
            expected_remote_row_count=2,
        )
        self.assertEqual(SYNCHRONIZED, result.status)
        self.assertTrue(result.remote_subset_verified)
        self.assertEqual(0, result.missing_row_count)
        self.assertIsNone(delta)

    def test_enabled_remote_row_is_rejected_by_format(self):
        result, delta = self.reconcile(remote(ROWS[:1], enabled=1), candidate(ROWS))
        self.assertEqual(FAIL_CLOSED, result.status)
        self.assertIn("INPUT_FORMAT_INVALID", result.reason_codes)
        self.assertIsNone(delta)

    def test_identity_mismatch_fails_closed(self):
        result, delta = self.reconcile(
            remote(ROWS[:1]), candidate(ROWS), expected_remote_sha256="0" * 64
        )
        self.assertEqual(FAIL_CLOSED, result.status)
        self.assertIn("REMOTE_IDENTITY_MISMATCH", result.reason_codes)
        self.assertIsNone(delta)

    def test_existing_delta_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote_path = root / "remote.sql"
            candidate_path = root / "candidate.sql"
            delta_path = root / "delta.sql"
            remote_bytes = remote(ROWS[:1])
            candidate_bytes = candidate(ROWS)
            remote_path.write_bytes(remote_bytes)
            candidate_path.write_bytes(candidate_bytes)
            delta_path.write_text("preserve", encoding="utf-8")
            result = reconcile_files(
                remote_path,
                candidate_path,
                delta_path,
                expected_remote_sha256=hashlib.sha256(remote_bytes).hexdigest(),
                expected_candidate_sha256=hashlib.sha256(candidate_bytes).hexdigest(),
                expected_remote_row_count=1,
                expected_candidate_row_count=2,
            )
            self.assertEqual(FAIL_CLOSED, result.status)
            self.assertEqual("preserve", delta_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
