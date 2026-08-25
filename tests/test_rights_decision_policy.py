from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import rights_decision_policy as policy  # noqa: E402


class RightsDecisionPolicyTests(unittest.TestCase):
    def assert_public(self, field: str, expected: str) -> None:
        self.assertEqual(policy.decision_for(field).public_display, expected)

    def test_a_title_approved(self): self.assert_public("title", policy.APPROVED)
    def test_b_product_main_image_approved(self): self.assert_public("product_main_image", policy.APPROVED)
    def test_c_dmm_books_image_prohibited(self): self.assert_public("dmm_books_product_image", policy.PROHIBITED)
    def test_d_actress_name_approved(self): self.assert_public("actress_name", policy.APPROVED)
    def test_e_actress_face_image_prohibited(self): self.assert_public("actress_api_face_image", policy.PROHIBITED)
    def test_f_review_numeric_approved(self):
        self.assert_public("review_count", policy.APPROVED); self.assert_public("review_average", policy.APPROVED)
    def test_g_review_text_prohibited(self): self.assert_public("user_review_text", policy.PROHIBITED)
    def test_h_description_prohibited(self): self.assert_public("product_description", policy.PROHIBITED)
    def test_i_derived_ranking_approved(self): self.assert_public("derived_ranking", policy.APPROVED)
    def test_j_raw_api_prohibited(self): self.assert_public("raw_api_response", policy.PROHIBITED)
    def test_k_api_id_prohibited(self): self.assert_public("api_id", policy.PROHIBITED)
    def test_l_affiliate_id_prohibited(self): self.assert_public("affiliate_id", policy.PROHIBITED)
    def test_m_query_context_prohibited(self): self.assert_public("query_context", policy.PROHIBITED)
    def test_n_lifecycle_pending(self): self.assert_public("lifecycle_status", policy.PENDING_SEPARATE_POLICY)
    def test_o_rank_semantics_pending(self): self.assert_public("rank_sort_semantics", policy.PENDING_SEPARATE_POLICY)
    def test_p_review_semantics_pending(self): self.assert_public("review_sort_semantics", policy.PENDING_SEPARATE_POLICY)
    def test_q_unknown_field_fails_closed(self):
        with self.assertRaisesRegex(KeyError, "UNKNOWN_RIGHTS_FIELD"): policy.decision_for("unknown")
    def test_r_public_and_semantic_status_are_separate(self):
        row = policy.decision_for("title"); self.assertEqual(row.public_display, policy.APPROVED); self.assertEqual(row.semantic_status, policy.NOT_APPLICABLE)
    def test_s_policy_version_fixed(self): self.assertEqual(policy.POLICY_VERSION, "0.1")
    def test_t_secret_bearing_fields_cannot_be_approved(self):
        for field in policy.SECRET_BEARING_FIELDS: self.assertEqual(policy.decision_for(field).public_display, policy.PROHIBITED)
    def test_u_affiliate_url_is_not_approved_public_field(self): self.assert_public("affiliate_url", policy.CONDITIONALLY_APPROVED)
    def test_v_price_and_analysis_are_candidates(self):
        for field in ("price", "derived_price_comparison", "derived_analysis"): self.assertTrue(policy.decision_for(field).future_public_data_candidate)
    def test_w_existing_rights_pending_fields_are_candidates(self):
        for field in ("title", "product_main_image", "product_page_url", "maker", "series", "actress_name", "genre"): self.assertTrue(policy.decision_for(field).future_public_data_candidate)
    def test_x_pending_rows_use_pending_evidence(self):
        for field in ("lifecycle_status", "rank_sort_semantics", "review_sort_semantics"): self.assertEqual(policy.decision_for(field).evidence_type, policy.SEPARATE_POLICY_PENDING)
    def test_y_matrix_self_validation(self): self.assertEqual(policy.validate_policy(), ())
    def test_z_secret_rule_detects_unsafe_replacement(self):
        unsafe = replace(policy.decision_for("api_id"), public_display=policy.APPROVED); self.assertTrue(unsafe.secret_bearing); self.assertIn(unsafe.public_display, {policy.APPROVED, policy.CONDITIONALLY_APPROVED})


if __name__ == "__main__":
    unittest.main()
