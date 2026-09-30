import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_expansion_d1_delta as subject  # noqa: E402


def candidate() -> bytes:
    lines = ["BEGIN TRANSACTION;"]
    for index in range(300):
        lines.append(
            "INSERT INTO affiliate_item_lookup (public_id, content_id, updated_at) VALUES "
            f"('itm_{index:024x}', 'cid{index}', '1970-01-01T00:00:00Z');"
        )
    lines.append("COMMIT;")
    return ("\n".join(lines) + "\n").encode()


def remote(*, conflict: bool = False) -> bytes:
    lines = ["PRAGMA defer_foreign_keys=TRUE;"]
    for index in range(200):
        content_id = "different" if conflict and index == 0 else f"cid{index}"
        lines.append(
            'INSERT INTO "affiliate_item_lookup" '
            '("public_id","content_id","rights_status","lifecycle_status",'
            '"verification_status","affiliate_enabled","updated_at") VALUES'
            f"('itm_{index:024x}','{content_id}','PENDING_SEPARATE_POLICY',"
            "'PENDING_OFFICIAL_CONFIRMATION','PENDING',0,'1970-01-01T00:00:00Z');"
        )
    for index in range(300, 310):
        lines.append(
            'INSERT INTO "affiliate_item_lookup" '
            '("public_id","content_id","rights_status","lifecycle_status",'
            '"verification_status","affiliate_enabled","updated_at") VALUES'
            f"('itm_{index:024x}','cid{index}','CONDITIONALLY_APPROVED',"
            "'RESOLVED','PASS',1,'2026-10-01T00:00:00Z');"
        )
    return ("\n".join(lines) + "\n").encode()


class ExpansionD1DeltaTests(unittest.TestCase):
    def assess(self, remote_bytes: bytes):
        candidate_bytes = candidate()
        schema = (ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql").read_bytes()
        return subject.build(
            remote_bytes, candidate_bytes, schema,
            expected_remote_sha256=hashlib.sha256(remote_bytes).hexdigest(),
            expected_candidate_sha256=hashlib.sha256(candidate_bytes).hexdigest(),
        )

    def test_preserves_remote_superset_and_adds_only_missing_candidate_rows(self):
        receipt, delta = self.assess(remote())
        self.assertEqual(receipt.status, subject.READY)
        self.assertEqual(receipt.remote_row_count, 210)
        self.assertEqual(receipt.exact_match_count, 200)
        self.assertEqual(receipt.delta_row_count, 100)
        self.assertEqual(receipt.final_row_count, 310)
        self.assertTrue(receipt.existing_rows_unchanged)
        self.assertTrue(receipt.new_rows_disabled_and_pending)
        self.assertTrue(receipt.runtime_eligibility_unchanged)
        self.assertFalse(receipt.production_write_performed)
        self.assertFalse(receipt.publication_allowed)
        self.assertIsNotNone(delta)

    def test_mapping_conflict_blocks(self):
        receipt, delta = self.assess(remote(conflict=True))
        self.assertEqual(receipt.status, subject.BLOCKED)
        self.assertIsNone(delta)

    def test_identity_mismatch_blocks(self):
        remote_bytes = remote()
        candidate_bytes = candidate()
        schema = (ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql").read_bytes()
        receipt, delta = subject.build(
            remote_bytes, candidate_bytes, schema,
            expected_remote_sha256="0" * 64,
            expected_candidate_sha256=hashlib.sha256(candidate_bytes).hexdigest(),
        )
        self.assertEqual(receipt.status, subject.BLOCKED)
        self.assertIsNone(delta)


if __name__ == "__main__":
    unittest.main()
