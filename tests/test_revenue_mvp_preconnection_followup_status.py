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
    def test_submission_remains_fail_closed(self):
        result = status.current_status()

        self.assertEqual(result.version, "0.1")
        self.assertEqual(result.status, status.SUBMITTED_AWAITING_RESPONSE)
        self.assertEqual(result.submitted_at, "2026-09-23T23:32:00+09:00")
        self.assertEqual(result.question_ids, status.QUESTION_IDS)
        self.assertFalse(result.response_received)
        self.assertFalse(result.live_connection_allowed)
        self.assertFalse(result.gate_unlock_allowed)
        self.assertFalse(result.secrets_transmitted)
        self.assertIn("OFFICIAL_RESPONSE_PENDING", result.reason_codes)

    def test_cli_emits_only_sanitized_state(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "revenue_mvp_preconnection_followup_status.py")],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)

        self.assertEqual(set(payload), {
            "version", "status", "submitted_at", "question_ids",
            "response_received", "live_connection_allowed",
            "gate_unlock_allowed", "secrets_transmitted", "reason_codes",
        })
        self.assertFalse(payload["live_connection_allowed"])
        self.assertFalse(payload["gate_unlock_allowed"])
        self.assertFalse(payload["secrets_transmitted"])


if __name__ == "__main__":
    unittest.main()
