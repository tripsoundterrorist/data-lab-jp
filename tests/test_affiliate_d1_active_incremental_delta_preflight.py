import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import affiliate_d1_active_incremental_delta_preflight as subject  # noqa: E402


ROWS = [
    ("itm_aaaaaaaaaaaaaaaaaaaaaaaa", "content-a"),
    ("itm_bbbbbbbbbbbbbbbbbbbbbbbb", "content-b"),
]


def candidate() -> bytes:
    return (
        "BEGIN TRANSACTION;\n"
        + "\n".join(
            "INSERT INTO affiliate_item_lookup (public_id, content_id, updated_at) "
            f"VALUES ('{public_id}', '{content_id}', '1970-01-01T00:00:00Z');"
            for public_id, content_id in ROWS
        )
        + "\nCOMMIT;\n"
    ).encode()


def remote() -> bytes:
    public_id, content_id = ROWS[0]
    return (
        "PRAGMA defer_foreign_keys=TRUE;\n"
        'INSERT INTO "affiliate_item_lookup" '
        '("public_id","content_id","rights_status","lifecycle_status",'
        '"verification_status","affiliate_enabled","updated_at") VALUES'
        f"('{public_id}','{content_id}','CONDITIONALLY_APPROVED','RESOLVED',"
        "'PASS',1,'2026-09-29T16:35:00Z');\n"
    ).encode()


def delta() -> bytes:
    public_id, content_id = ROWS[1]
    return (
        "INSERT INTO affiliate_item_lookup (public_id, content_id, updated_at) VALUES\n"
        f"('{public_id}', '{content_id}', '1970-01-01T00:00:00Z');\n"
    ).encode()


class ActiveIncrementalDeltaPreflightTests(unittest.TestCase):
    def assess(self, delta_bytes=None):
        r, c, d = remote(), candidate(), delta_bytes or delta()
        schema = (ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql").read_bytes()
        return subject.assess(
            r, c, d, schema,
            expected_remote_sha256=hashlib.sha256(r).hexdigest(),
            expected_candidate_sha256=hashlib.sha256(c).hexdigest(),
            expected_delta_sha256=hashlib.sha256(d).hexdigest(),
            expected_remote_row_count=1,
            expected_candidate_row_count=2,
        )

    def test_preserves_active_rows_and_adds_disabled_pending_rows(self):
        result = self.assess()
        self.assertEqual(result.status, subject.READY)
        self.assertTrue(result.existing_rows_unchanged)
        self.assertTrue(result.new_rows_disabled_and_pending)
        self.assertTrue(result.runtime_eligibility_unchanged)
        self.assertFalse(result.production_write_performed)
        self.assertFalse(result.publication_allowed)

    def test_non_exact_delta_fails_closed(self):
        changed = delta().replace(b"1970-01-01", b"2026-01-01")
        self.assertEqual(self.assess(changed).status, subject.FAIL_CLOSED)


if __name__ == "__main__":
    unittest.main()
