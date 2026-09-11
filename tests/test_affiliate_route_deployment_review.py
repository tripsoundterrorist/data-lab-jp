from contextlib import redirect_stdout
from io import StringIO
import inspect
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_route_deployment_review as review  # noqa: E402


def ready_evidence() -> review.RouteDeploymentEvidence:
    return review.RouteDeploymentEvidence(
        True, True, True, True, True, True, True, True, True, True, True, False
    )


class AffiliateRouteDeploymentReviewTests(unittest.TestCase):
    def test_current_packet_reports_exact_remaining_boundaries(self):
        result = review.assess(review.current_evidence())
        self.assertEqual(review.BLOCKED, result.status)
        self.assertTrue(result.d1_lookup_ready)
        self.assertTrue(result.secret_binding_names_ready)
        self.assertFalse(result.runtime_boundary_ready)
        self.assertFalse(result.rollback_ready)
        self.assertFalse(result.deployment_review_candidate)
        for reason in (
            "PAGES_FUNCTION_ENTRYPOINT_NOT_PRESENT",
            "RATE_LIMIT_BINDING_NOT_CONFIGURED",
            "PROXIMATE_PR_DISCLOSURE_NOT_CONNECTED",
            "ROLLBACK_PLAN_NOT_RECORDED",
        ):
            self.assertIn(reason, result.reason_codes)
        self.assertNotIn("D1_LOOKUP_NOT_READY", result.reason_codes)
        self.assertNotIn("SECRET_BINDING_NAMES_NOT_READY", result.reason_codes)
        self.assertNotIn("TRUSTED_CLIENT_KEY_DERIVATION_NOT_PRESENT", result.reason_codes)
        self.assertNotIn("WORKERS_RUNTIME_PROVIDER_NOT_PRESENT", result.reason_codes)

    def test_complete_packet_reaches_separate_approval_only(self):
        result = review.assess(ready_evidence())
        self.assertEqual(review.READY, result.status)
        self.assertTrue(result.deployment_review_candidate)
        self.assertTrue(result.runtime_boundary_ready)
        self.assertTrue(result.rollback_ready)
        self.assertFalse(result.production_deployment_allowed)
        self.assertFalse(result.route_activation_allowed)
        self.assertFalse(result.affiliate_activation_allowed)
        self.assertFalse(result.paid_plan_change_allowed)

    def test_each_missing_guard_blocks(self):
        for field in inspect.signature(review.RouteDeploymentEvidence).parameters:
            if field == "production_deployment_performed":
                continue
            evidence = ready_evidence()
            changed = review.RouteDeploymentEvidence(
                **{**evidence.__dict__, field: False}
            )
            with self.subTest(field=field):
                result = review.assess(changed)
                self.assertEqual(review.BLOCKED, result.status)
                self.assertFalse(result.deployment_review_candidate)

    def test_unapproved_deployment_blocks(self):
        evidence = ready_evidence()
        evidence = review.RouteDeploymentEvidence(
            **{**evidence.__dict__, "production_deployment_performed": True}
        )
        result = review.assess(evidence)
        self.assertEqual(review.BLOCKED, result.status)
        self.assertIn("UNAPPROVED_PRODUCTION_DEPLOYMENT_DETECTED", result.reason_codes)

    def test_malformed_input_fails_closed_and_schema_is_sanitized(self):
        fields = set(inspect.signature(review.RouteDeploymentEvidence).parameters)
        for forbidden in (
            "secret_value",
            "secret_values",
            "url",
            "database_id",
            "account_id",
            "public_id",
        ):
            self.assertNotIn(forbidden, fields)
        for value in (None, {}, review.RouteDeploymentEvidence(*([True] * 11), 0)):
            with self.subTest(value=value):
                result = review.assess(value)
                self.assertEqual(review.FAIL_CLOSED, result.status)
                self.assertFalse(result.production_deployment_allowed)

    def test_cli_is_machine_readable_and_non_deploying(self):
        output = StringIO()
        with redirect_stdout(output):
            return_code = review.main()
        result = json.loads(output.getvalue())
        self.assertEqual(0, return_code)
        self.assertEqual(review.BLOCKED, result["status"])
        self.assertFalse(result["production_deployment_allowed"])
        self.assertFalse(result["paid_plan_change_allowed"])


if __name__ == "__main__":
    unittest.main()
