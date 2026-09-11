from contextlib import redirect_stdout
from io import StringIO
import inspect
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_pages_secret_state as state  # noqa: E402


class AffiliatePagesSecretStateTests(unittest.TestCase):
    def test_current_state_records_exact_production_secret_names(self):
        result = state.assess(state.current_evidence())
        self.assertEqual(state.READY, result.status)
        self.assertTrue(result.production_environment_checked)
        self.assertTrue(result.values_not_read)
        self.assertEqual(2, result.required_binding_count)
        self.assertEqual(2, result.observed_required_binding_count)
        self.assertEqual(
            ("DMM_AFFILIATE_ID", "DMM_API_ID"), result.verified_binding_names
        )
        self.assertEqual(
            ("REQUIRED_SECRET_BINDING_NAMES_VERIFIED",), result.reason_codes
        )
        self.assertFalse(result.secret_configuration_allowed)
        self.assertFalse(result.deployment_allowed)

    def test_exact_required_names_are_review_ready_only(self):
        evidence = state.PagesSecretEvidence(
            True,
            True,
            ("DMM_API_ID", "DMM_AFFILIATE_ID"),
        )
        result = state.assess(evidence)
        self.assertEqual(state.READY, result.status)
        self.assertEqual(2, result.observed_required_binding_count)
        self.assertEqual(
            ("DMM_AFFILIATE_ID", "DMM_API_ID"), result.verified_binding_names
        )
        self.assertFalse(result.secret_configuration_allowed)
        self.assertFalse(result.deployment_allowed)

    def test_unknown_missing_duplicate_and_unchecked_states_do_not_pass(self):
        for evidence in (
            state.PagesSecretEvidence(True, True, ("DMM_API_ID",)),
            state.PagesSecretEvidence(True, True, ("DMM_API_ID", "UNKNOWN")),
            state.PagesSecretEvidence(True, True, ("DMM_API_ID", "DMM_API_ID")),
            state.PagesSecretEvidence(False, True, ("DMM_API_ID", "DMM_AFFILIATE_ID")),
            state.PagesSecretEvidence(True, False, ("DMM_API_ID", "DMM_AFFILIATE_ID")),
        ):
            with self.subTest(evidence=evidence):
                result = state.assess(evidence)
                self.assertNotEqual(state.READY, result.status)
                self.assertEqual((), result.verified_binding_names)
                self.assertFalse(result.secret_configuration_allowed)
                self.assertFalse(result.deployment_allowed)

    def test_contract_has_no_secret_value_field_and_cli_is_sanitized(self):
        fields = set(inspect.signature(state.PagesSecretEvidence).parameters)
        self.assertNotIn("secret_values", fields)
        self.assertNotIn("api_id", fields)
        output = StringIO()
        with redirect_stdout(output):
            return_code = state.main()
        result = json.loads(output.getvalue())
        self.assertEqual(0, return_code)
        self.assertEqual(state.READY, result["status"])
        self.assertNotIn("secret_values", result)

    def test_malformed_input_fails_closed(self):
        for evidence in (
            None,
            {"observed_binding_names": ()},
            state.PagesSecretEvidence(True, True, ("lowercase",)),
            state.PagesSecretEvidence(1, True, ()),
        ):
            with self.subTest(evidence=evidence):
                result = state.assess(evidence)
                self.assertEqual(state.FAIL_CLOSED, result.status)
                self.assertEqual((), result.verified_binding_names)


if __name__ == "__main__":
    unittest.main()
