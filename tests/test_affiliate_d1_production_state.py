from contextlib import redirect_stdout
from io import StringIO
import inspect
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_d1_production_state as state  # noqa: E402


class AffiliateD1ProductionStateTests(unittest.TestCase):
    def test_current_evidence_is_ready_but_never_authorizes_change(self):
        result = state.assess(state.current_evidence())
        self.assertEqual(state.READY, result.status)
        self.assertTrue(result.lookup_ready)
        self.assertTrue(result.free_plan_compatible)
        self.assertEqual(865, result.row_count)
        self.assertTrue(result.all_rows_disabled)
        self.assertTrue(result.all_rows_pending)
        self.assertTrue(result.runtime_eligibility_empty)
        self.assertTrue(result.exact_candidate_mapping_verified)
        self.assertFalse(result.cloudflare_write_allowed)
        self.assertFalse(result.deployment_allowed)
        self.assertFalse(result.paid_plan_change_allowed)

    def test_each_guard_blocks(self):
        for changes, reason in (
            ({"free_plan_confirmed": False}, "FREE_PLAN_NOT_CONFIRMED"),
            ({"table_present": False}, "D1_SCHEMA_NOT_READY"),
            ({"eligible_view_present": False}, "D1_SCHEMA_NOT_READY"),
            ({"row_count": 860, "pending_row_count": 860}, "D1_ROW_COUNT_MISMATCH"),
            ({"pending_row_count": 860}, "D1_PENDING_STATE_MISMATCH"),
            ({"enabled_row_count": 1}, "D1_AFFILIATE_ROW_ENABLED"),
            ({"eligible_row_count": 1}, "D1_RUNTIME_ELIGIBILITY_NOT_EMPTY"),
            ({"exact_candidate_mapping_verified": False}, "D1_EXACT_MAPPING_NOT_VERIFIED"),
        ):
            with self.subTest(changes=changes):
                evidence = state.current_evidence()
                evidence = state.D1ProductionEvidence(**{**evidence.__dict__, **changes})
                result = state.assess(evidence)
                self.assertEqual(state.BLOCKED, result.status)
                self.assertFalse(result.lookup_ready)
                self.assertIn(reason, result.reason_codes)
                self.assertFalse(result.cloudflare_write_allowed)
                self.assertFalse(result.deployment_allowed)
                self.assertFalse(result.paid_plan_change_allowed)

    def test_malformed_input_fails_closed_without_sensitive_fields(self):
        fields = set(inspect.signature(state.D1ProductionEvidence).parameters)
        self.assertFalse(any(name in fields for name in ("database_id", "account_id", "url", "secret")))
        for value in (
            None,
            {"row_count": 861},
            state.D1ProductionEvidence(True, "WRONG", True, True, 861, 861, 0, 0, True),
            state.D1ProductionEvidence(True, state.EXPECTED_BINDING_NAME, True, True, True, 861, 0, 0, True),
        ):
            with self.subTest(value=value):
                result = state.assess(value)
                self.assertEqual(state.FAIL_CLOSED, result.status)
                self.assertFalse(result.lookup_ready)

    def test_cli_is_sanitized_and_non_mutating(self):
        output = StringIO()
        with redirect_stdout(output):
            return_code = state.main()
        result = json.loads(output.getvalue())
        self.assertEqual(0, return_code)
        self.assertEqual(state.READY, result["status"])
        self.assertNotIn("database_id", result)
        self.assertNotIn("account_id", result)
        self.assertNotIn("url", result)


if __name__ == "__main__":
    unittest.main()
