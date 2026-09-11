from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_runtime_deployment_preflight as preflight  # noqa: E402


def ready_candidate() -> preflight.AffiliateDeploymentCandidate:
    return preflight.AffiliateDeploymentCandidate(
        platform_adapter_candidate=True,
        private_lookup_import_preflight_ready=True,
        secret_binding_names=("DMM_API_ID", "DMM_AFFILIATE_ID"),
        data_binding_names=("AFFILIATE_ITEM_LOOKUP",),
        route_path="/go/:public_id",
        allowed_methods=("GET", "HEAD"),
        redirect_status=302,
        per_client_rate_limit=True,
        requests_per_minute=30,
        burst_limit=5,
        log_redaction_enabled=True,
        response_cache_disabled=True,
        official_answer_candidate=True,
        runtime_provider_connected=True,
        runtime_resolution_connected=True,
        pr_disclosure_available=True,
    )


class AffiliateRuntimeDeploymentPreflightTests(unittest.TestCase):
    def test_current_state_records_inert_d1_but_remains_blocked(self):
        result = preflight.assess_preflight(preflight.current_input())

        self.assertEqual(result.status, preflight.BLOCKED)
        self.assertFalse(result.deployment_candidate)
        self.assertFalse(result.production_deployment_allowed)
        self.assertTrue(result.platform_adapter_candidate)
        self.assertTrue(result.private_lookup_import_preflight_ready)
        self.assertEqual(result.secret_binding_name_count, 0)
        self.assertEqual(result.data_binding_name_count, 1)
        self.assertNotIn("PRIVATE_LOOKUP_IMPORT_PREFLIGHT_NOT_READY", result.reason_codes)
        self.assertNotIn("DATA_BINDING_NOT_READY", result.reason_codes)
        self.assertIn("SECRET_BINDINGS_NOT_READY", result.reason_codes)
        self.assertNotIn("OFFICIAL_ANSWER_GATE_CLOSED", result.reason_codes)
        self.assertIn(
            "AFFILIATE_RUNTIME_CHAIN_NOT_CONNECTED", result.reason_codes
        )

    def test_complete_sanitized_candidate_reaches_review_only(self):
        result = preflight.assess_preflight(ready_candidate())

        self.assertEqual(
            result.status, preflight.READY_FOR_DEPLOYMENT_REVIEW
        )
        self.assertTrue(result.deployment_candidate)
        self.assertFalse(result.production_deployment_allowed)
        self.assertTrue(result.platform_adapter_candidate)
        self.assertTrue(result.private_lookup_import_preflight_ready)
        self.assertTrue(result.route_configured)
        self.assertTrue(result.rate_limit_configured)
        self.assertTrue(result.runtime_chain_connected)
        self.assertEqual(result.secret_binding_name_count, 2)
        self.assertEqual(result.data_binding_name_count, 1)
        self.assertEqual(
            result.reason_codes, ("AFFILIATE_DEPLOYMENT_PREFLIGHT_PASS",)
        )

    def test_secret_values_or_unknown_names_are_never_echoed(self):
        candidate = ready_candidate()
        candidate = preflight.AffiliateDeploymentCandidate(
            **{
                **candidate.__dict__,
                "secret_binding_names": (
                    "DMM_API_ID",
                    "actual-secret-value",
                ),
            }
        )

        result = preflight.assess_preflight(candidate)
        output = json.dumps(result.to_dict(), sort_keys=True)

        self.assertEqual(result.status, preflight.BLOCKED)
        self.assertEqual(result.secret_binding_name_count, 0)
        self.assertIn("SECRET_BINDINGS_NOT_READY", result.reason_codes)
        self.assertNotIn("actual-secret-value", output)

    def test_route_requires_exact_path_methods_and_temporary_redirect(self):
        candidate = ready_candidate()
        candidate = preflight.AffiliateDeploymentCandidate(
            **{
                **candidate.__dict__,
                "allowed_methods": ("GET", "POST"),
                "redirect_status": 301,
            }
        )

        result = preflight.assess_preflight(candidate)

        self.assertFalse(result.route_configured)
        self.assertIn("AFFILIATE_ROUTE_NOT_READY", result.reason_codes)

    def test_rate_limit_is_per_client_and_bounded(self):
        for changes in (
            {"per_client_rate_limit": False},
            {"requests_per_minute": 61},
            {"requests_per_minute": True},
            {"burst_limit": 11},
            {"requests_per_minute": 4, "burst_limit": 5},
        ):
            with self.subTest(changes=changes):
                candidate = ready_candidate()
                candidate = preflight.AffiliateDeploymentCandidate(
                    **{**candidate.__dict__, **changes}
                )
                result = preflight.assess_preflight(candidate)
                self.assertFalse(result.rate_limit_configured)
                self.assertIn("RATE_LIMIT_NOT_READY", result.reason_codes)

    def test_each_activation_guard_blocks_review(self):
        for field, reason in (
            (
                "platform_adapter_candidate",
                "PLATFORM_ADAPTER_CANDIDATE_NOT_READY",
            ),
            (
                "private_lookup_import_preflight_ready",
                "PRIVATE_LOOKUP_IMPORT_PREFLIGHT_NOT_READY",
            ),
            ("log_redaction_enabled", "LOG_REDACTION_NOT_READY"),
            ("response_cache_disabled", "RESPONSE_CACHE_POLICY_NOT_READY"),
            ("official_answer_candidate", "OFFICIAL_ANSWER_GATE_CLOSED"),
            (
                "runtime_provider_connected",
                "AFFILIATE_RUNTIME_CHAIN_NOT_CONNECTED",
            ),
            (
                "runtime_resolution_connected",
                "AFFILIATE_RUNTIME_CHAIN_NOT_CONNECTED",
            ),
            ("pr_disclosure_available", "PR_DISCLOSURE_NOT_READY"),
        ):
            with self.subTest(field=field):
                candidate = ready_candidate()
                candidate = preflight.AffiliateDeploymentCandidate(
                    **{**candidate.__dict__, field: False}
                )
                result = preflight.assess_preflight(candidate)
                self.assertEqual(result.status, preflight.BLOCKED)
                self.assertIn(reason, result.reason_codes)

    def test_malformed_candidate_fails_closed(self):
        result = preflight.assess_preflight({"secret": "value"})

        self.assertEqual(result.status, preflight.FAIL_CLOSED)
        self.assertFalse(result.production_deployment_allowed)
        self.assertFalse(result.platform_adapter_candidate)
        self.assertFalse(result.private_lookup_import_preflight_ready)
        self.assertEqual(
            result.reason_codes,
            ("AFFILIATE_DEPLOYMENT_PREFLIGHT_INTERNAL_ERROR",),
        )
        self.assertNotIn("value", json.dumps(result.to_dict()))

    def test_cli_is_machine_readable_and_non_deploying(self):
        output = StringIO()
        with redirect_stdout(output):
            return_code = preflight.main()

        self.assertEqual(return_code, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], preflight.BLOCKED)
        self.assertFalse(result["production_deployment_allowed"])
        self.assertTrue(result["private_lookup_import_preflight_ready"])
        self.assertEqual(1, result["data_binding_name_count"])


if __name__ == "__main__":
    unittest.main()
