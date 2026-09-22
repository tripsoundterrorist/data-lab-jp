from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_cta_runtime_inert_integration as integration

NOW = datetime(2026, 9, 22, 6, 0, tzinfo=timezone.utc)
PUBLIC_ID = "itm_000000000000000000000000"


def assess(**changes):
    values = {"version": integration.VERSION, "method": "GET", "path": "/go/" + PUBLIC_ID,
        "request_body_present": False, "official_answer_candidate": True,
        "publication_gate_overall_eligible": True, "runtime_chain_connected": True,
        "rate_limit_allowed": True, "pr_disclosure_available": True, "evaluated_at": NOW}
    values.update(changes)
    return integration.assess(**values)


class InertIntegrationTests(unittest.TestCase):
    def test_production_entrypoint_blocks_without_internal_approved_context(self):
        result = assess()
        self.assertEqual(result.status, integration.BLOCKED)
        self.assertTrue(result.click_revalidation_assessed)
        self.assertIsNone(result.response_status_candidate)
        self.assertFalse(result.redirect_activation_allowed)

    def test_route_guards_stop_before_click_assessment(self):
        result = assess(method="POST")
        self.assertEqual(result.status, integration.BLOCKED)
        self.assertFalse(result.click_revalidation_assessed)

    def test_caller_injected_resolver_or_bundle_are_not_accepted(self):
        for name, value in (("trusted_resolver", lambda _value: {}), ("selection_bundle", object())):
            with self.subTest(name=name):
                with self.assertRaises(TypeError):
                    assess(**{name: value})


if __name__ == "__main__":
    unittest.main()
