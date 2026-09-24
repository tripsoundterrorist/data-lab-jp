from pathlib import Path
import json
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import revenue_mvp_official_followup_status as status  # noqa: E402
from official_blocker_policy import LIFECYCLE_BLOCKER, SORT_BLOCKER  # noqa: E402


class OfficialFollowupStatusTests(unittest.TestCase):
    def test_received_response_is_recorded_without_gate_resolution(self):
        result = status.current_status()
        self.assertEqual(
            result.status, status.RESPONSE_RECEIVED_PARTIALLY_RESOLVED
        )
        self.assertEqual(result.covered_blockers,
                         (LIFECYCLE_BLOCKER, SORT_BLOCKER))
        self.assertTrue(result.response_received)
        self.assertFalse(result.official_semantics_resolved)
        self.assertFalse(result.gate_unlock_allowed)

    def test_safe_contract_contains_no_message_or_account_metadata(self):
        result = status.current_status().to_dict()
        self.assertEqual(
            set(result),
            {"version", "status", "submitted_on", "covered_blockers",
             "response_received", "official_semantics_resolved",
             "gate_unlock_allowed", "reason_codes"},
        )
        rendered = json.dumps(result).casefold()
        for forbidden in ("email", "sender", "account", "affiliate_id", "api_id"):
            self.assertNotIn(forbidden, rendered)

    def test_missing_or_invalid_reviewed_evidence_fails_closed(self):
        missing = mock.Mock()
        missing.read_text.side_effect = OSError("private path")
        with mock.patch.object(status, "EVIDENCE_PATH", missing):
            result = status.current_status()
        self.assertEqual(result.status, status.FAIL_CLOSED)
        self.assertFalse(result.response_received)
        self.assertFalse(result.official_semantics_resolved)
        self.assertFalse(result.gate_unlock_allowed)
        self.assertNotIn("private", json.dumps(result.to_dict()).casefold())

    def test_same_counts_with_swapped_unresolved_question_fails_closed(self):
        value = json.loads(status.EVIDENCE_PATH.read_text(encoding="utf-8"))
        lifecycle = next(
            entry for entry in value
            if entry["referenced_blocker"] == LIFECYCLE_BLOCKER
        )
        lifecycle["answered_questions"]["HISTORICAL_METADATA_RETENTION"] = (
            "RESOLVED"
        )
        lifecycle["answered_questions"]["CID_ZERO_RESULT_MEANING"] = (
            "PARTIALLY_RESOLVED"
        )
        lifecycle["unanswered_questions"] = ["CID_ZERO_RESULT_MEANING"]
        lifecycle["explicit_confirmations"].remove("CID_ZERO_RESULT_MEANING")
        lifecycle["explicit_confirmations"].append(
            "HISTORICAL_METADATA_RETENTION"
        )
        swapped = mock.Mock()
        swapped.read_text.return_value = json.dumps(value)
        with mock.patch.object(status, "EVIDENCE_PATH", swapped):
            result = status.current_status()
        self.assertEqual(result.status, status.FAIL_CLOSED)
        self.assertFalse(result.response_received)


if __name__ == "__main__":
    unittest.main()
