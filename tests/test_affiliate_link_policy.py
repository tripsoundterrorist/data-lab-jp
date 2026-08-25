from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_link_policy as policy  # noqa: E402
from rights_decision_policy import CONDITIONALLY_APPROVED, decision_for  # noqa: E402


def assess(**changes):
    values = {
        "policy_version": "0.1",
        "rights_status": CONDITIONALLY_APPROVED,
        "publication_context": "WEB_UI",
        "has_affiliate_url": True,
        "lifecycle_status": "PENDING_OFFICIAL_CONFIRMATION",
        "verification_status": "PASS",
        "publication_gate_status": "CLOSED",
        "pr_disclosure_available": True,
    }
    values.update(changes)
    return policy.assess_affiliate_link(**values)


class AffiliateLinkPolicyTests(unittest.TestCase):
    def test_a_version(self): self.assertEqual(policy.POLICY_VERSION, "0.1")
    def test_b_rights_conditionally_approved(self): self.assertEqual(decision_for("affiliate_url").public_display, CONDITIONALLY_APPROVED)
    def test_c_public_json_blocked(self): self.assertEqual(assess(publication_context="PUBLIC_JSON").link_status, policy.LINK_BLOCKED)
    def test_d_public_data_blocked(self): self.assertEqual(assess(publication_context="PUBLIC_DATA").link_status, policy.LINK_BLOCKED)
    def test_e_static_artifact_blocked(self): self.assertEqual(assess(publication_context="STATIC_ARTIFACT").link_status, policy.LINK_BLOCKED)
    def test_f_api_export_blocked(self): self.assertEqual(assess(publication_context="API_RESPONSE_EXPORT").link_status, policy.LINK_BLOCKED)
    def test_g_web_ui_candidate_pending(self): self.assertTrue(assess().ui_candidate)
    def test_h_no_pr_blocked(self): self.assertEqual(assess(pr_disclosure_available=False).link_status, policy.LINK_BLOCKED)
    def test_i_pr_available_candidate(self): self.assertTrue(assess(pr_disclosure_available=True).ui_candidate)
    def test_j_gate_closed_render_false(self): self.assertFalse(assess(lifecycle_status="RESOLVED").production_render_allowed)
    def test_k_gate_open_fixture_render_candidate(self): self.assertTrue(assess(lifecycle_status="RESOLVED", publication_gate_status="OPEN").production_render_allowed)
    def test_l_link_presence_not_availability(self): self.assertIn("AVAILABILITY_NOT_INFERRED", assess().reason_codes)
    def test_m_link_absence_not_ineligible(self): self.assertIn("AFFILIATE_INELIGIBILITY_NOT_INFERRED", assess(has_affiliate_url=False).reason_codes)
    def test_n_lifecycle_pending(self): self.assertEqual(assess().link_status, policy.LINK_PENDING_LIFECYCLE_POLICY)
    def test_o_lifecycle_resolved(self): self.assertEqual(assess(lifecycle_status="RESOLVED").link_status, policy.LINK_AVAILABLE_FOR_UI)
    def test_p_unknown_rights(self): self.assertEqual(assess(rights_status="UNKNOWN").link_status, policy.INVALID_INPUT)
    def test_q_unknown_context(self): self.assertEqual(assess(publication_context="EMAIL").link_status, policy.INVALID_INPUT)
    def test_r_prohibited_rights(self): self.assertEqual(assess(rights_status="PROHIBITED").link_status, policy.LINK_BLOCKED)
    def test_s_approved_is_not_conditional(self): self.assertEqual(assess(rights_status="APPROVED").link_status, policy.LINK_BLOCKED)
    def test_t_raw_url_input_rejected(self): self.assertEqual(assess(affiliate_url="https://example.invalid").link_status, policy.INVALID_INPUT)
    def test_u_url_absent_from_output(self): self.assertNotIn("url", repr(assess().to_dict()).lower())
    def test_v_content_id_input_rejected(self): self.assertEqual(assess(content_id="x").link_status, policy.INVALID_INPUT)
    def test_w_title_input_rejected(self): self.assertEqual(assess(title="x").link_status, policy.INVALID_INPUT)
    def test_x_credential_input_rejected(self): self.assertEqual(assess(credential="x").link_status, policy.INVALID_INPUT)
    def test_y_path_input_rejected(self): self.assertEqual(assess(absolute_path="C:/x").link_status, policy.INVALID_INPUT)
    def test_z_raw_exception_input_rejected(self): self.assertEqual(assess(raw_exception="x").link_status, policy.INVALID_INPUT)
    def test_aa_reasons_deterministic(self): self.assertEqual(assess().reason_codes, tuple(sorted(assess().reason_codes)))
    def test_ab_unknown_version(self): self.assertEqual(assess(policy_version="9").link_status, policy.INVALID_INPUT)
    def test_ac_gate_unlock_absent(self): self.assertNotIn("gate_unlock", assess().to_dict())
    def test_ad_lifecycle_unlock_absent(self): self.assertNotIn("lifecycle_unlock", assess().to_dict())
    def test_ae_publication_status_absent(self): self.assertNotIn("publication_status", assess().to_dict())
    def test_af_ui_candidate_differs_from_production(self): self.assertEqual((assess().ui_candidate, assess().production_render_allowed), (True, False))
    def test_ag_affiliate_eligibility_not_confirmed(self): self.assertIn("AFFILIATE_ELIGIBILITY_NOT_CONFIRMED", assess(lifecycle_status="RESOLVED").reason_codes)
    def test_ah_api_visibility_not_an_input(self): self.assertEqual(assess(api_visible=True).link_status, policy.INVALID_INPUT)
    def test_ai_pr_required_fixed(self): self.assertTrue(assess().pr_disclosure_required)
    def test_aj_safe_result_exact_fields(self): self.assertEqual(set(assess().to_dict()), {"policy_version", "link_status", "ui_candidate", "production_render_allowed", "pr_disclosure_required", "lifecycle_semantics_resolved", "reason_codes"})

    def test_ak_internal_exception_safe(self):
        with mock.patch.object(policy, "_evaluate", side_effect=RuntimeError("secret traceback")):
            result = assess()
        self.assertEqual(result.reason_codes, ("INTERNAL_POLICY_ERROR",)); self.assertNotIn("secret", repr(result.to_dict()))

    def test_al_verification_failed_blocked(self): self.assertEqual(assess(verification_status="FAILED").link_status, policy.LINK_BLOCKED)
    def test_am_verification_pending(self): self.assertEqual(assess(verification_status="PENDING").link_status, policy.LINK_PENDING_LIFECYCLE_POLICY)
    def test_an_unknown_verification(self): self.assertEqual(assess(verification_status="UNKNOWN").link_status, policy.INVALID_INPUT)
    def test_ao_unknown_gate(self): self.assertEqual(assess(publication_gate_status="PASS").link_status, policy.INVALID_INPUT)
    def test_ap_unknown_lifecycle(self): self.assertEqual(assess(lifecycle_status="UNKNOWN").link_status, policy.INVALID_INPUT)
    def test_aq_boolean_contract(self): self.assertEqual(assess(has_affiliate_url=1).link_status, policy.INVALID_INPUT)
    def test_ar_no_link_is_not_ui_candidate(self): self.assertFalse(assess(has_affiliate_url=False).ui_candidate)
    def test_as_pending_never_production_render(self): self.assertFalse(assess(publication_gate_status="OPEN").production_render_allowed)
    def test_at_available_not_purchasable_confirmed(self): self.assertIn("PURCHASABILITY_NOT_CONFIRMED", assess(lifecycle_status="RESOLVED").reason_codes)


if __name__ == "__main__":
    unittest.main()
