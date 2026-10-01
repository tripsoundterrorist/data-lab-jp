from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_expansion_activation_progress as subject  # noqa: E402


class ExpansionActivationProgressTests(unittest.TestCase):
    def test_current_progress_matches_verified_post_batch_state(self):
        result = subject.current_progress()
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.candidate_count, 300)
        self.assertEqual(result.initial_completed_count, 5)
        self.assertEqual(result.initial_remaining_count, 173)
        self.assertEqual(result.retry_waiting_count, 75)
        self.assertEqual(result.active_count, 49)
        self.assertEqual(result.legacy_pending_review_count, 3)
        self.assertEqual(result.redirect_target_count, 124)
        self.assertEqual(result.runtime_redirect_count, 49)
        self.assertEqual(result.next_initial_batch_size, 5)
        self.assertEqual(result.remaining_initial_batch_count, 35)
        self.assertFalse(result.api_request_performed)
        self.assertFalse(result.d1_write_performed)
        self.assertFalse(result.live_execution_allowed)
        self.assertTrue(result.explicit_live_approval_required)

    def test_identity_mismatch_blocks(self):
        original = subject.EXPECTED_CURRENT_SHA256
        try:
            subject.EXPECTED_CURRENT_SHA256 = "0" * 64
            result = subject.current_progress()
        finally:
            subject.EXPECTED_CURRENT_SHA256 = original
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertEqual(result.reason_codes, ("INPUT_IDENTITY_MISMATCH",))

    def test_malformed_candidate_blocks_without_writes(self):
        result = subject.assess(b"", b"", b"", b"")
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertFalse(result.d1_write_performed)
        self.assertFalse(result.live_execution_allowed)


if __name__ == "__main__":
    unittest.main()
