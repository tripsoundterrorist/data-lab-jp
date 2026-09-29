import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import revenue_mvp_current_state as state


class CurrentRevenueStateTests(unittest.TestCase):
    def setUp(self):
        self.receipt = json.loads(state.RECEIPT_PATH.read_text(encoding="utf-8"))
        self.artifact = state.ARTIFACT_PATH.read_bytes()
        self.preflight = state.affiliate_runtime_deployment_preflight.assess_preflight(
            state.affiliate_runtime_deployment_preflight.current_input()
        )
        self.route = state.affiliate_route_deployment_review.assess(
            state.affiliate_route_deployment_review.current_evidence()
        )
        self.d1 = state.affiliate_d1_production_state.assess(
            state.affiliate_d1_production_state.current_evidence()
        )

    def assess(self, receipt=None, artifact=None):
        return state.assess(
            self.receipt if receipt is None else receipt,
            self.artifact if artifact is None else artifact,
            self.preflight, self.route, self.d1,
        )

    def test_current_exact_surface_is_approved_one_cta_pending_edge(self):
        result = self.assess()
        self.assertEqual(result.status, state.APPROVED_CANARY_PENDING_EDGE)
        self.assertTrue(result.limited_surface_live)
        self.assertEqual(result.live_item_count, 100)
        self.assertTrue(result.affiliate_runtime_candidate_ready)
        self.assertTrue(result.cta_allowed)
        self.assertTrue(result.affiliate_integration_allowed)
        self.assertFalse(result.production_write_allowed)
        self.assertEqual(result.next_action, "VERIFY_ONE_CTA_CANARY_AT_EDGE")

    def test_artifact_mismatch_fails_closed(self):
        result = self.assess(artifact=self.artifact + b"\n")
        self.assertEqual(result.status, state.FAIL_CLOSED)
        self.assertFalse(result.limited_surface_live)

    def test_receipt_cannot_open_affiliate_gate(self):
        receipt = copy.deepcopy(self.receipt)
        receipt["cta_allowed"] = True
        result = self.assess(receipt=receipt)
        self.assertEqual(result.status, state.APPROVED_CANARY_PENDING_EDGE)
        self.assertTrue(result.affiliate_integration_allowed)

    def test_cli_current_state(self):
        result = state.current_state()
        self.assertEqual(result.status, state.APPROVED_CANARY_PENDING_EDGE)


if __name__ == "__main__":
    unittest.main()

