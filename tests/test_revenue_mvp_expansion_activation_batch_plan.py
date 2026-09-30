from pathlib import Path
import sqlite3
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_expansion_activation_batch_plan as subject  # noqa: E402
from tests.test_revenue_mvp_expansion_d1_delta import candidate, full_remote  # noqa: E402


class ExpansionActivationBatchPlanTests(unittest.TestCase):
    def artifacts(self):
        before = full_remote()
        connection = sqlite3.connect(":memory:")
        connection.executescript(before.decode())
        for index in range(200, 300):
            connection.execute(
                "INSERT INTO affiliate_item_lookup (public_id,content_id,updated_at) VALUES (?,?,?)",
                (f"itm_{index:024x}", f"cid{index}", "1970-01-01T00:00:00Z"),
            )
        schema = (ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql").read_text()
        lines = ["PRAGMA defer_foreign_keys=TRUE;", schema]
        for row in connection.execute(
            "SELECT public_id,content_id,rights_status,lifecycle_status,verification_status,affiliate_enabled,updated_at FROM affiliate_item_lookup"
        ):
            lines.append(
                'INSERT INTO "affiliate_item_lookup" '
                '("public_id","content_id","rights_status","lifecycle_status",'
                '"verification_status","affiliate_enabled","updated_at") VALUES'
                f"('{row[0]}','{row[1]}','{row[2]}','{row[3]}','{row[4]}',{row[5]},'{row[6]}');"
            )
        connection.close()
        return before, ("\n".join(lines) + "\n").encode()

    def test_new_rows_are_separate_nonexecuting_batches(self):
        before, after = self.artifacts()
        result = subject.assess(
            before, after, candidate(),
            (ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql").read_bytes(),
            expected_new_count=100,
        )
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.new_initial_validation_count, 100)
        self.assertEqual(result.initial_batch_count, 20)
        self.assertFalse(result.api_request_performed)
        self.assertFalse(result.d1_write_performed)
        self.assertFalse(result.activation_allowed)

    def test_mutated_new_row_blocks(self):
        before, after = self.artifacts()
        after = after.replace(b"'PENDING',0,'1970-01-01", b"'PASS',1,'1970-01-01", 1)
        result = subject.assess(
            before, after, candidate(),
            (ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql").read_bytes(),
            expected_new_count=100,
        )
        self.assertEqual(result.status, subject.BLOCKED)


if __name__ == "__main__":
    unittest.main()
