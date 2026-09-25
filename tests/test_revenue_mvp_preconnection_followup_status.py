import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import revenue_mvp_preconnection_followup_status as status  # noqa: E402


class PreconnectionFollowupStatusTests(unittest.TestCase):
    def test_received_response_remains_fail_closed_pending_review(self):
        result = status.current_status()

        self.assertEqual(result.version, "0.2")
        self.assertEqual(result.status, status.RESPONSE_RECEIVED_REVIEW_REQUIRED)
        self.assertEqual(result.submitted_at, "2026-09-23T23:32:00+09:00")
        self.assertEqual(result.responded_on, "2026-09-25")
        self.assertEqual(result.question_ids, status.QUESTION_IDS)
        self.assertEqual(result.live_single_request_permission, "YES")
        self.assertEqual(result.user_agent_requirement, "NO")
        self.assertTrue(result.response_received)
        self.assertFalse(result.live_connection_allowed)
        self.assertFalse(result.gate_unlock_allowed)
        self.assertFalse(result.secrets_transmitted)
        self.assertTrue(result.compliance_review_required)
        self.assertTrue(result.explicit_connection_approval_required)
        self.assertIn("OFFICIAL_RESPONSE_RECEIVED", result.reason_codes)

    def test_cli_emits_only_sanitized_state(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "revenue_mvp_preconnection_followup_status.py")],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)

        self.assertEqual(set(payload), {
            "version", "status", "submitted_at", "responded_on", "question_ids",
            "live_single_request_permission", "user_agent_requirement",
            "response_received", "live_connection_allowed",
            "gate_unlock_allowed", "secrets_transmitted",
            "compliance_review_required", "explicit_connection_approval_required",
            "reason_codes",
        })
        self.assertFalse(payload["live_connection_allowed"])
        self.assertFalse(payload["gate_unlock_allowed"])
        self.assertFalse(payload["secrets_transmitted"])

    def test_missing_or_tampered_evidence_fails_closed(self):
        from unittest import mock

        with mock.patch("pathlib.Path.read_text", side_effect=OSError("private")):
            result = status.current_status()
        self.assertEqual(result.status, "FAIL_CLOSED")
        self.assertFalse(result.response_received)
        self.assertFalse(result.live_connection_allowed)
        self.assertNotIn("private", json.dumps(result.to_dict()))


if __name__ == "__main__":
    unittest.main()
