from pathlib import Path
import sqlite3
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_expansion_initial_selection as subject  # noqa: E402
from tests.test_revenue_mvp_expansion_d1_delta import full_remote  # noqa: E402


def snapshots():
    before = full_remote()
    connection = sqlite3.connect(":memory:")
    connection.executescript(before.decode())
    for index in range(178):
        value = index + 400
        connection.execute(
            "INSERT INTO affiliate_item_lookup (public_id,content_id,updated_at) VALUES (?,?,?)",
            (f"itm_{value:024x}", f"new{value}", "1970-01-01T00:00:00Z"),
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


class InitialSelectionTests(unittest.TestCase):
    def test_deterministic_five_item_batch(self):
        before, after = snapshots()
        receipt, payload = subject.build(
            before, after,
            (ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql").read_bytes(),
            batch_index=0,
        )
        self.assertEqual(receipt.status, subject.READY)
        self.assertEqual(receipt.selected_count, 5)
        self.assertEqual(receipt.batch_count, 36)
        self.assertEqual(len(payload.decode().splitlines()), 5)
        self.assertFalse(receipt.identifiers_exposed)
        self.assertFalse(receipt.activation_allowed)

    def test_out_of_range_blocks(self):
        before, after = snapshots()
        receipt, payload = subject.build(
            before, after,
            (ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql").read_bytes(),
            batch_index=36,
        )
        self.assertEqual(receipt.status, subject.BLOCKED)
        self.assertIsNone(payload)


if __name__ == "__main__": unittest.main()
