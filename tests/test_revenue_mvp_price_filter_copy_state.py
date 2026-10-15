"""Offline copy recognition is not publication, live verification or eligibility."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_current_state as state
import revenue_mvp_price_filter_copy_candidate as subject


class PriceFilterCopyStateTests(unittest.TestCase):
    def setUp(self):
        self.source = state.ARTIFACT_PATH.read_bytes()
        self.candidate, _ = subject.build(self.source)
        self.receipt = json.loads(state.RECEIPT_PATH.read_text(encoding="utf-8"))
        self.live = json.loads(state.REFRESHED_PRODUCT_CARD_LIVE_EVIDENCE_PATH.read_text(encoding="utf-8"))
        self.preflight = state.affiliate_runtime_deployment_preflight.assess_preflight(
            state.affiliate_runtime_deployment_preflight.current_input())
        self.route = state.affiliate_route_deployment_review.assess(
            state.affiliate_route_deployment_review.current_evidence())
        self.d1 = state.affiliate_d1_production_state.assess(
            state.affiliate_d1_production_state.current_evidence())

    def assess(self, artifact=None, **kwargs):
        return state.assess(self.receipt, self.candidate if artifact is None else artifact,
                            self.preflight, self.route, self.d1, self.live, **kwargs)

    def assert_no_authority(self, result):
        for name in ("limited_surface_live", "edge_artifact_verified", "cta_allowed",
                     "affiliate_integration_allowed", "production_write_allowed", "paid_plan_change_allowed"):
            self.assertIs(getattr(result, name), False, name)
        self.assertIsNone(result.live_item_count)

    def test_exact_copy_is_pending_without_authority_or_input_mutation(self):
        before = copy.deepcopy((self.receipt, self.live))
        result = self.assess()
        self.assertEqual(result.status, state.PRICE_COPY_PENDING)
        self.assertIn("CURRENT_DISPLAY_AND_ELIGIBILITY_NOT_VERIFIED", result.reason_codes)
        self.assert_no_authority(result)
        self.assertEqual(before, (self.receipt, self.live))
        self.assertEqual(state.ARTIFACT_PATH.read_bytes(), self.source)

    def test_forged_observation_cannot_grant_copy_live_authority(self):
        result = self.assess(price_display_observation={"verified": True})
        self.assertEqual(result.status, state.PRICE_COPY_PENDING)
        self.assert_no_authority(result)

    def test_missing_product_card_context_remains_fail_closed(self):
        self.live = {}
        result = self.assess()
        self.assertEqual(result.status, state.FAIL_CLOSED)
        self.assertEqual(result.reason_codes, ("PRICE_COPY_SOURCE_CONTEXT_INVALID",))
        self.assert_no_authority(result)

    def test_wrong_historical_live_hash_remains_fail_closed(self):
        self.live["production"]["artifact_sha256"] = "0" * 64
        result = self.assess()
        self.assertEqual(result.status, state.FAIL_CLOSED)
        self.assert_no_authority(result)

    def test_unrelated_candidate_change_is_not_recognized(self):
        for candidate in (self.candidate + b"changed", self.candidate.replace(b"/go/", b"/xx/", 1)):
            with self.subTest(length=len(candidate)):
                result = self.assess(candidate)
                self.assertEqual(result.status, state.FAIL_CLOSED)
                self.assert_no_authority(result)
                with self.assertRaises(ValueError):
                    subject.recover_source(candidate)

    def test_recovery_rebuilds_exact_source_with_windows_line_endings(self):
        candidate = subject._canonical(self.candidate).replace(b"\n", b"\r\n")
        source = subject.recover_source(candidate)
        self.assertEqual(subject._canonical(source), subject._canonical(self.source))
        self.assertEqual(subject.build(source)[0], candidate)
        self.assertEqual(self.assess(candidate).status, state.PRICE_COPY_PENDING)

    def test_current_state_selects_matching_historical_context_but_not_live_authority(self):
        fake = Mock()
        fake.read_bytes.return_value = self.candidate
        with patch.object(state, "ARTIFACT_PATH", fake):
            result = state.current_state()
        self.assertEqual(result.status, state.PRICE_COPY_PENDING)
        self.assert_no_authority(result)

    def test_old_display_state_and_recovery_input_boundary_unchanged(self):
        self.assertEqual(self.assess(self.source).status, state.PRICE_DISPLAY_PENDING)
        for value in (self.source, None, "html", b"\xff", b"x" * (1024 * 1024 + 1)):
            with self.subTest(kind=type(value).__name__), self.assertRaises(ValueError):
                subject.recover_source(value)


if __name__ == "__main__":
    unittest.main()
