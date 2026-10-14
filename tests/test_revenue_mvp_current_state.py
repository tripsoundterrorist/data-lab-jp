import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import revenue_mvp_current_state as state
from tests.revenue_mvp_historical_fixture import historical_artifact


class CurrentRevenueStateTests(unittest.TestCase):
    def setUp(self):
        self.receipt = json.loads(state.RECEIPT_PATH.read_text(encoding="utf-8"))
        # Historical approval tests use pinned old bytes, not current LIVE status.
        self.artifact = historical_artifact(state.ARTIFACT_PATH.read_bytes())
        self.preflight = state.affiliate_runtime_deployment_preflight.assess_preflight(
            state.affiliate_runtime_deployment_preflight.current_input()
        )
        self.route = state.affiliate_route_deployment_review.assess(
            state.affiliate_route_deployment_review.current_evidence()
        )
        self.d1 = state.affiliate_d1_production_state.assess(
            state.affiliate_d1_production_state.current_evidence()
        )
        self.live = json.loads(state.REFRESHED_PRODUCT_CARD_LIVE_EVIDENCE_PATH.read_text(encoding="utf-8"))

    def assess(self, receipt=None, artifact=None, live=None):
        return state.assess(
            self.receipt if receipt is None else receipt,
            self.artifact if artifact is None else artifact,
            self.preflight, self.route, self.d1,
            self.live if live is None else live,
        )

    def test_approved_refresh_is_live_and_edge_verified(self):
        result = self.assess()
        self.assertEqual(result.status, state.PRODUCT_CARD_LIVE_LOCAL_SCHEDULER_ACTIVE)
        self.assertTrue(result.limited_surface_live)
        self.assertTrue(result.edge_artifact_verified)
        self.assertEqual(result.live_item_count, 100)
        self.assertTrue(result.affiliate_runtime_candidate_ready)
        self.assertTrue(result.cta_allowed)
        self.assertTrue(result.affiliate_integration_allowed)
        self.assertFalse(result.production_write_allowed)
        self.assertEqual(result.next_action, "MONITOR_DAILY_REVALIDATION_AND_REVENUE_FUNNEL")
        self.assertEqual(result.affiliate_d1_enabled_row_count, 100)

    def test_artifact_mismatch_fails_closed(self):
        result = self.assess(artifact=self.artifact + b"\n")
        self.assertEqual(result.status, state.FAIL_CLOSED)
        self.assertFalse(result.limited_surface_live)

    def test_receipt_cannot_open_affiliate_gate(self):
        receipt = copy.deepcopy(self.receipt)
        receipt["cta_allowed"] = True
        result = self.assess(receipt=receipt)
        self.assertEqual(result.status, state.PRODUCT_CARD_LIVE_LOCAL_SCHEDULER_ACTIVE)
        self.assertTrue(result.affiliate_integration_allowed)

    def test_invalid_live_evidence_falls_back_to_pending_edge(self):
        live = copy.deepcopy(self.live)
        live["production"]["cta_count"] = 99
        result = self.assess(live=live)
        self.assertEqual(result.status, state.PRODUCT_CARD_CANARY_PENDING_EDGE)
        self.assertFalse(result.edge_artifact_verified)

    def test_cli_current_state(self):
        result = state.current_state()
        from hashlib import sha256
        actual=state.price_transition.canonical(state.ARTIFACT_PATH.read_bytes())
        if sha256(actual).hexdigest()==state.price_transition.CANDIDATE:
            self.assertEqual(result.status,state.PRICE_DISPLAY_PENDING)
            self.assertFalse(result.limited_surface_live)
            self.assertFalse(result.edge_artifact_verified)
            self.assertFalse(result.cta_allowed)
            self.assertFalse(result.affiliate_integration_allowed)
            self.assertFalse(result.production_write_allowed)
        else:
            self.assertEqual(sha256(actual).hexdigest(),state.REFRESHED_PRODUCT_CARD_SHA256)
            self.assertEqual(result.status, state.PRODUCT_CARD_LIVE_LOCAL_SCHEDULER_ACTIVE)

    def transition(self, candidate=None, history=None, live=None):
        baseline = state.price_transition.canonical(self.artifact)
        corrected = baseline.replace('円</p>'.encode(), '円〜</p>'.encode())
        return state.assess_price_display_candidate(
            self.receipt, baseline, corrected if candidate is None else candidate,
            self.preflight, self.route, self.d1,
            self.live if live is None else live,
            {"items_artifact_sha256": state.REFRESHED_PRODUCT_CARD_SHA256}
                if history is None else history,
        )

    def test_display_candidate_separates_history_from_live_authority(self):
        previous = copy.deepcopy(self.live)
        result = self.transition()
        self.assertEqual(result["status"], "DISPLAY_COMPATIBILITY_REVIEW_ONLY")
        self.assertEqual(result["display"]["status"],
                         "CANDIDATE_PENDING_LIVE_DISPLAY_VERIFICATION")
        for key in ("historical_state_is_candidate_live_proof",
                    "candidate_live_eligibility_verified", "publication_allowed",
                    "production_write_allowed", "global_publication_gate_changed"):
            self.assertFalse(result[key])
        self.assertEqual(self.live, previous)

    def test_display_candidate_does_not_bypass_existing_assess(self):
        candidate = state.price_transition.canonical(self.artifact).replace(
            '円</p>'.encode(), '円〜</p>'.encode())
        result = self.assess(artifact=candidate)
        self.assertEqual(result.status, state.PRICE_DISPLAY_PENDING)
        self.assertFalse(result.limited_surface_live)
        self.assertFalse(result.edge_artifact_verified)
        self.assertFalse(result.cta_allowed)
        self.assertFalse(result.affiliate_integration_allowed)
        self.assertFalse(result.production_write_allowed)

    def test_display_compatibility_blocks_unrelated_changes_and_relabelled_history(self):
        self.assertEqual(self.transition(candidate=b"other")["status"], "BLOCKED")
        self.assertEqual(self.transition(history={"items_artifact_sha256":
            state.price_transition.CANDIDATE})["status"], "BLOCKED")

    def test_display_compatibility_requires_valid_historical_scope(self):
        live = copy.deepcopy(self.live)
        live["production"]["cta_count"] = 99
        self.assertEqual(self.transition(live=live)["status"], "BLOCKED")

    def test_current_state_routes_corrected_artifact_to_separate_pending_review(self):
        candidate = state.price_transition.canonical(self.artifact).replace(
            '円</p>'.encode(), '円〜</p>'.encode())
        original_read = Path.read_bytes
        def read(path):
            return candidate if path == state.ARTIFACT_PATH else original_read(path)
        with patch.object(Path, "read_bytes", read):
            result = state.current_state()
        self.assertEqual(result.status, state.PRICE_DISPLAY_PENDING)
        self.assertFalse(result.edge_artifact_verified)
        self.assertFalse(result.affiliate_integration_allowed)

    def test_candidate_display_observation_cannot_open_existing_affiliate_state(self):
        from tests.test_revenue_mvp_price_display_transition import Response
        candidate = state.price_transition.canonical(self.artifact).replace(
            '円</p>'.encode(), '円〜</p>'.encode())
        with patch.object(state.price_transition.urllib.request, "urlopen",
                          return_value=Response(candidate)):
            observation = state.price_transition.capture_public_page()
        result = state.assess(self.receipt,candidate,self.preflight,self.route,self.d1,
                              self.live,price_display_observation=observation)
        self.assertEqual(result.status,state.PRICE_DISPLAY_PENDING)
        self.assertIn("DISPLAY_ONLY_NOT_ELIGIBILITY_OR_PUBLICATION_AUTHORITY",result.reason_codes)
        self.assertFalse(result.cta_allowed)
        self.assertFalse(result.edge_artifact_verified)

    def test_forged_candidate_observation_blocks_current_state(self):
        candidate = state.price_transition.canonical(self.artifact).replace(
            '円</p>'.encode(), '円〜</p>'.encode())
        result = state.assess(self.receipt,candidate,self.preflight,self.route,self.d1,
                              self.live,price_display_observation={"verified":True})
        self.assertEqual(result.status,state.FAIL_CLOSED)


if __name__ == "__main__":
    unittest.main()

