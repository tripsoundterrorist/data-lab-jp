import json
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_one_shot_verification_evidence as evidence  # noqa: E402


class OneShotVerificationEvidenceTests(unittest.TestCase):
    def test_current_receipt_is_ready_without_activation(self):
        result = evidence.assess_evidence()
        self.assertEqual(result.status, evidence.READY)
        self.assertTrue(result.request_verified)
        self.assertEqual(result.api_calls, 1)
        self.assertFalse(result.retry_performed)
        self.assertFalse(result.writes_performed)
        self.assertFalse(result.gate_unlock_allowed)
        self.assertFalse(result.production_activation_allowed)

    def test_permissive_or_multi_call_receipt_fails_closed(self):
        for key, value in (("api_calls", 2), ("api_calls", True),
                           ("request_attempt_limit", True),
                           ("items_returned", True),
                           ("review_present", True),
                           ("retry_performed", True),
                           ("database_write_performed", True),
                           ("gate_unlock_allowed", True)):
            payload = json.loads(evidence.EVIDENCE.read_text(encoding="utf-8"))
            payload[key] = value
            path = mock.Mock()
            path.read_text.return_value = json.dumps(payload)
            with self.subTest(key=key), mock.patch.object(evidence, "EVIDENCE", path):
                result = evidence.assess_evidence()
            self.assertEqual(result.status, evidence.BLOCKED)
            self.assertFalse(result.gate_unlock_allowed)

    def test_private_error_is_not_exposed(self):
        path = mock.Mock()
        path.read_text.side_effect = OSError("private-marker")
        with mock.patch.object(evidence, "EVIDENCE", path):
            result = evidence.assess_evidence()
        self.assertNotIn("private-marker", json.dumps(result.to_dict()))


if __name__ == "__main__":
    unittest.main()
