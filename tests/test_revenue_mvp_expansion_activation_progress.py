from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_expansion_activation_progress as subject  # noqa: E402


class ExpansionActivationProgressTests(unittest.TestCase):
    def test_current_progress_matches_verified_post_batch_state(self):
        result = subject.current_progress()
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.candidate_count, 300)
        self.assertEqual(result.initial_completed_count, 178)
        self.assertEqual(result.initial_remaining_count, 0)
        self.assertEqual(result.retry_waiting_count, 0)
        self.assertEqual(result.active_count, 300)
        self.assertEqual(result.legacy_pending_review_count, 0)
        self.assertEqual(result.redirect_target_count, 300)
        self.assertEqual(result.runtime_redirect_count, 300)
        self.assertEqual(result.next_initial_batch_size, 0)
        self.assertEqual(result.remaining_initial_batch_count, 0)
        self.assertFalse(result.api_request_performed)
        self.assertFalse(result.d1_write_performed)
        self.assertFalse(result.live_execution_allowed)
        self.assertTrue(result.explicit_live_approval_required)

    def test_invalid_final_evidence_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "invalid.json"
            invalid.write_text(json.dumps({"version": "0.1"}), encoding="utf-8")
            with mock.patch.object(subject, "FINAL_COVERAGE", invalid):
                result = subject.current_progress()
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertEqual(result.reason_codes, ("FINAL_COVERAGE_EVIDENCE_INVALID",))

    def test_malformed_candidate_blocks_without_writes(self):
        result = subject.assess(b"", b"", b"", b"")
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertFalse(result.d1_write_performed)
        self.assertFalse(result.live_execution_allowed)


if __name__ == "__main__":
    unittest.main()
