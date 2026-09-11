from pathlib import Path
import inspect
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import affiliate_route_rollback_plan as plan  # noqa: E402


class AffiliateRouteRollbackPlanTests(unittest.TestCase):
    def test_route_detachment_is_first_and_plan_is_non_executing(self):
        result = plan.build_plan()
        self.assertEqual(result.status, plan.READY)
        self.assertEqual(result.ordered_actions[0], "DETACH_EXACT_AFFILIATE_WORKER_ROUTE")
        self.assertFalse(result.executable)
        self.assertFalse(result.production_write_allowed)
        self.assertFalse(result.billing_change_allowed)

    def test_preserves_site_d1_secrets_and_requires_explicit_reactivation(self):
        result = plan.build_plan()
        self.assertIn("HOME_AND_INFORMATION_PAGES_AVAILABLE", result.verification_checks)
        self.assertIn("D1_SCHEMA_UNCHANGED", result.verification_checks)
        self.assertIn("SECRET_VALUES_NOT_READ_OR_EXPOSED", result.verification_checks)
        self.assertIn("EXPLICIT_REACTIVATION_APPROVAL", result.reactivation_requirements)

    def test_module_has_no_execution_capability(self):
        source = inspect.getsource(plan)
        for forbidden in (
            "subprocess", "urllib", "requests", "os.system", "wrangler",
            "cloudflare.com", "DELETE FROM", "DROP TABLE", "UPDATE ",
        ):
            self.assertNotIn(forbidden, source)

    def test_safe_output_contains_no_resource_identity(self):
        encoded = json.dumps(plan.build_plan().to_dict())
        for forbidden in ("database_id", "account_id", "token", "secret_value", "https://"):
            self.assertNotIn(forbidden, encoded)


if __name__ == "__main__":
    unittest.main()
