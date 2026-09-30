from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_expansion_d1_delta as delta_builder  # noqa: E402
import revenue_mvp_expansion_d1_prewrite_gate as subject  # noqa: E402
from tests.test_revenue_mvp_expansion_d1_delta import candidate, remote  # noqa: E402


class ExpansionD1PrewriteGateTests(unittest.TestCase):
    def artifacts(self):
        remote_bytes = remote()
        candidate_bytes = candidate()
        schema = (ROOT / "runtime-candidates" / "affiliate-item-lookup-schema.sql").read_bytes()
        receipt, delta = delta_builder.build(
            remote_bytes, candidate_bytes, schema,
            expected_remote_sha256=hashlib.sha256(remote_bytes).hexdigest(),
            expected_candidate_sha256=hashlib.sha256(candidate_bytes).hexdigest(),
        )
        self.assertEqual(receipt.status, delta_builder.READY)
        self.assertIsNotNone(delta)
        return remote_bytes, candidate_bytes, delta, schema, receipt

    def test_fresh_exact_delta_is_ready_for_separate_write_review(self):
        remote_bytes, candidate_bytes, delta, schema, receipt = self.artifacts()
        now = datetime.now(timezone.utc)
        result = subject.assess(
            remote_bytes, candidate_bytes, delta, schema,
            expected_remote_sha256=hashlib.sha256(remote_bytes).hexdigest(),
            expected_candidate_sha256=hashlib.sha256(candidate_bytes).hexdigest(),
            expected_delta_sha256=hashlib.sha256(delta).hexdigest(),
            exported_at=now - timedelta(seconds=10), evaluated_at=now,
            expected_remote_row_count=receipt.remote_row_count,
            expected_delta_row_count=receipt.delta_row_count,
            expected_final_row_count=receipt.final_row_count,
        )
        self.assertEqual(result.status, subject.READY)
        self.assertTrue(result.exact_delta_verified)
        self.assertFalse(result.production_write_performed)
        self.assertFalse(result.publication_allowed)

    def test_stale_export_blocks(self):
        remote_bytes, candidate_bytes, delta, schema, receipt = self.artifacts()
        now = datetime.now(timezone.utc)
        result = subject.assess(
            remote_bytes, candidate_bytes, delta, schema,
            expected_remote_sha256=hashlib.sha256(remote_bytes).hexdigest(),
            expected_candidate_sha256=hashlib.sha256(candidate_bytes).hexdigest(),
            expected_delta_sha256=hashlib.sha256(delta).hexdigest(),
            exported_at=now - timedelta(seconds=901), evaluated_at=now,
            expected_remote_row_count=receipt.remote_row_count,
            expected_delta_row_count=receipt.delta_row_count,
            expected_final_row_count=receipt.final_row_count,
        )
        self.assertEqual(result.status, subject.BLOCKED)

    def test_changed_delta_blocks(self):
        remote_bytes, candidate_bytes, delta, schema, receipt = self.artifacts()
        now = datetime.now(timezone.utc)
        changed = delta.replace(b"1970-01-01", b"2026-01-01", 1)
        result = subject.assess(
            remote_bytes, candidate_bytes, changed, schema,
            expected_remote_sha256=hashlib.sha256(remote_bytes).hexdigest(),
            expected_candidate_sha256=hashlib.sha256(candidate_bytes).hexdigest(),
            expected_delta_sha256=hashlib.sha256(changed).hexdigest(),
            exported_at=now, evaluated_at=now,
            expected_remote_row_count=receipt.remote_row_count,
            expected_delta_row_count=receipt.delta_row_count,
            expected_final_row_count=receipt.final_row_count,
        )
        self.assertEqual(result.status, subject.BLOCKED)


if __name__ == "__main__":
    unittest.main()
