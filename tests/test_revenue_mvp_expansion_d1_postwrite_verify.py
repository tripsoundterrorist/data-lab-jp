import hashlib
from pathlib import Path
import sqlite3
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_expansion_d1_postwrite_verify as subject  # noqa: E402
from tests.test_revenue_mvp_expansion_d1_delta import candidate, full_remote  # noqa: E402


class ExpansionD1PostwriteVerificationTests(unittest.TestCase):
    def artifacts(self):
        before = full_remote()
        candidate_bytes = candidate()
        connection = sqlite3.connect(":memory:")
        connection.executescript(before.decode())
        for index in range(200, 300):
            connection.execute(
                "INSERT INTO affiliate_item_lookup (public_id,content_id,updated_at) VALUES (?,?,?)",
                (f"itm_{index:024x}", f"cid{index}", "1970-01-01T00:00:00Z"),
            )
        after_lines = ["PRAGMA defer_foreign_keys=TRUE;"]
        schema = (ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql").read_text()
        after_lines.append(schema)
        for row in connection.execute(
            "SELECT public_id,content_id,rights_status,lifecycle_status,verification_status,affiliate_enabled,updated_at FROM affiliate_item_lookup"
        ):
            after_lines.append(
                'INSERT INTO "affiliate_item_lookup" '
                '("public_id","content_id","rights_status","lifecycle_status",'
                '"verification_status","affiliate_enabled","updated_at") VALUES'
                f"('{row[0]}','{row[1]}','{row[2]}','{row[3]}','{row[4]}',{row[5]},'{row[6]}');"
            )
        connection.close()
        return before, ("\n".join(after_lines) + "\n").encode(), candidate_bytes

    def assess(self, after_change=None):
        before, after, candidate_bytes = self.artifacts()
        if after_change is not None:
            after = after_change(after)
        return subject.verify(
            before, after, candidate_bytes,
            (ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql").read_bytes(),
            expected_before_sha256=hashlib.sha256(before).hexdigest(),
            expected_after_sha256=hashlib.sha256(after).hexdigest(),
            expected_candidate_sha256=hashlib.sha256(candidate_bytes).hexdigest(),
            expected_before_row_count=210,
            expected_after_row_count=310,
            expected_new_row_count=100,
        )

    def test_exact_disabled_insert_is_verified(self):
        result = self.assess()
        self.assertEqual(result.status, subject.VERIFIED)
        self.assertTrue(result.existing_rows_unchanged)
        self.assertTrue(result.new_rows_disabled_and_pending)
        self.assertFalse(result.publication_allowed)

    def test_changed_existing_row_blocks(self):
        result = self.assess(lambda data: data.replace(b"'cid0'", b"'changed'", 1))
        self.assertEqual(result.status, subject.BLOCKED)


if __name__ == "__main__":
    unittest.main()
