from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ui_security_disclosure_policy as policy  # noqa: E402


def upstream(allowed=False):
    return {
        "handoff_version": "0.1",
        "render_status": "RENDER_ALLOWED" if allowed else "RENDER_BLOCKED",
        "render_candidate": True,
        "render_allowed": allowed,
        "pr_disclosure_required": True,
        "target_context": "WEB_UI",
        "reason_codes": ["DELEGATED_RENDER_CONDITIONS_SATISFIED" if allowed else "ADAPTER_PRODUCTION_RENDER_BLOCKED"],
    }


def assess(**changes):
    values = {
        "policy_version": "0.1", "handoff_result": upstream(),
        "link_type": "AFFILIATE_LINK", "disclosure_available": True,
        "disclosure_proximate": True, "disclosure_visible": True,
        "external_indicator_available": True, "target_blank": True,
        "rel_tokens": ("noopener", "noreferrer", "sponsored"),
        "cta_semantic": "VIEW_PRODUCT", "prohibited_patterns": (),
        "user_initiated_navigation": True, "availability_claim": False,
        "purchasability_claim": False, "affiliate_eligibility_claim": False,
    }
    values.update(changes)
    return policy.assess_ui_security(**values)


class UISecurityDisclosurePolicyTests(unittest.TestCase):
    def test_a_version(self): self.assertEqual(policy.POLICY_VERSION, "0.1")
    def test_b_current_upstream_blocked(self): self.assertEqual(assess().ui_security_status, policy.BLOCKED_UPSTREAM)
    def test_c_affiliate_disclosure_required(self): self.assertTrue(assess().disclosure_required)
    def test_d_normal_external(self): self.assertTrue(assess(link_type="NORMAL_EXTERNAL_LINK").external_indicator_required)
    def test_e_internal_link(self): self.assertFalse(assess(link_type="INTERNAL_LINK").external_indicator_required)
    def test_f_external_indicator_required(self): self.assertTrue(assess().external_indicator_required)
    def test_g_noopener_required(self): self.assertIn("noopener", assess().required_rel_tokens)
    def test_h_noreferrer_required(self): self.assertIn("noreferrer", assess().required_rel_tokens)
    def test_i_sponsored_required(self): self.assertIn("sponsored", assess().required_rel_tokens)

    def open_assess(self, **changes): return assess(handoff_result=upstream(True), **changes)

    def test_j_missing_disclosure(self): self.assertEqual(self.open_assess(disclosure_available=False).ui_security_status, policy.UI_SECURITY_BLOCKED)
    def test_k_hidden_disclosure(self): self.assertEqual(self.open_assess(disclosure_visible=False).ui_security_status, policy.UI_SECURITY_BLOCKED)
    def test_l_distant_disclosure(self): self.assertEqual(self.open_assess(disclosure_proximate=False).ui_security_status, policy.UI_SECURITY_BLOCKED)
    def test_m_automatic_redirect(self): self.assertIn("AUTOMATIC_REDIRECT", self.open_assess(prohibited_patterns=("AUTOMATIC_REDIRECT",)).prohibited_pattern_codes)
    def test_n_click_interception(self): self.assertIn("CLICK_INTERCEPTION", self.open_assess(prohibited_patterns=("CLICK_INTERCEPTION",)).prohibited_pattern_codes)
    def test_o_fake_download(self): self.assertIn("FAKE_DOWNLOAD_BUTTON", self.open_assess(prohibited_patterns=("FAKE_DOWNLOAD_BUTTON",)).prohibited_pattern_codes)
    def test_p_fake_close(self): self.assertIn("FAKE_CLOSE_BUTTON", self.open_assess(prohibited_patterns=("FAKE_CLOSE_BUTTON",)).prohibited_pattern_codes)
    def test_q_deceptive_urgency(self): self.assertEqual(self.open_assess(prohibited_patterns=("DECEPTIVE_URGENCY",)).ui_security_status, policy.UI_SECURITY_BLOCKED)
    def test_r_fake_scarcity(self): self.assertEqual(self.open_assess(prohibited_patterns=("FAKE_SCARCITY",)).ui_security_status, policy.UI_SECURITY_BLOCKED)
    def test_s_preselected_consent(self): self.assertEqual(self.open_assess(prohibited_patterns=("PRESELECTED_CONSENT",)).ui_security_status, policy.UI_SECURITY_BLOCKED)
    def test_t_misleading_cta(self): self.assertEqual(self.open_assess(cta_semantic="DOWNLOAD").ui_security_status, policy.UI_SECURITY_BLOCKED)
    def test_u_destination_transparent(self): self.assertEqual(self.open_assess(cta_semantic="OPEN_PRODUCT_PAGE").ui_security_status, policy.UI_SECURITY_PASS)
    def test_v_blank_without_noopener(self): self.assertEqual(self.open_assess(rel_tokens=("noreferrer", "sponsored")).ui_security_status, policy.UI_SECURITY_BLOCKED)
    def test_w_blank_without_noreferrer(self): self.assertEqual(self.open_assess(rel_tokens=("noopener", "sponsored")).ui_security_status, policy.UI_SECURITY_BLOCKED)
    def test_x_contradictory_internal(self): self.assertEqual(self.open_assess(link_type="INTERNAL_LINK").ui_security_status, policy.UI_SECURITY_BLOCKED)
    def test_y_unknown_link_type(self): self.assertEqual(self.open_assess(link_type="UNKNOWN").ui_security_status, policy.INVALID_INPUT)
    def test_z_gate_bypass_impossible(self): self.assertFalse(assess().render_allowed)
    def test_aa_lifecycle_not_output(self): self.assertNotIn("lifecycle", assess().to_dict())
    def test_ab_availability_claim_blocked(self): self.assertEqual(self.open_assess(availability_claim=True).ui_security_status, policy.UI_SECURITY_BLOCKED)
    def test_ac_purchasability_claim_blocked(self): self.assertEqual(self.open_assess(purchasability_claim=True).ui_security_status, policy.UI_SECURITY_BLOCKED)
    def test_ad_eligibility_claim_blocked(self): self.assertEqual(self.open_assess(affiliate_eligibility_claim=True).ui_security_status, policy.UI_SECURITY_BLOCKED)
    def test_ae_url_not_input(self): self.assertNotIn("url", policy.assess_ui_security.__annotations__)
    def test_af_url_not_output(self): self.assertNotIn("url", repr(assess().to_dict()).lower())
    def test_ag_title_extra_rejected(self): self.assertEqual(assess(title="x").ui_security_status, policy.INVALID_INPUT)
    def test_ah_content_id_extra_rejected(self): self.assertEqual(assess(content_id="x").ui_security_status, policy.INVALID_INPUT)
    def test_ai_product_id_extra_rejected(self): self.assertEqual(assess(product_id="x").ui_security_status, policy.INVALID_INPUT)
    def test_aj_affiliate_id_extra_rejected(self): self.assertEqual(assess(affiliate_id="x").ui_security_status, policy.INVALID_INPUT)
    def test_ak_credential_extra_rejected(self): self.assertEqual(assess(credential="x").ui_security_status, policy.INVALID_INPUT)
    def test_al_path_extra_rejected(self): self.assertEqual(assess(absolute_path="x").ui_security_status, policy.INVALID_INPUT)
    def test_am_raw_exception_extra_rejected(self): self.assertEqual(assess(raw_exception="x").ui_security_status, policy.INVALID_INPUT)
    def test_an_deterministic_reasons(self): self.assertEqual(assess().reason_codes, tuple(sorted(assess().reason_codes)))
    def test_ao_safe_output_allowlist(self): self.assertEqual(set(assess().to_dict()), {"policy_version", "ui_security_status", "render_allowed", "disclosure_required", "external_indicator_required", "required_rel_tokens", "prohibited_pattern_codes", "reason_codes"})
    def test_ap_unknown_version(self): self.assertEqual(assess(policy_version="9").ui_security_status, policy.INVALID_INPUT)

    def test_aq_internal_exception_safe(self):
        with mock.patch.object(policy, "_evaluate", side_effect=RuntimeError("secret traceback")):
            result = assess()
        self.assertEqual(result.reason_codes, ("INTERNAL_UI_SECURITY_ERROR",)); self.assertNotIn("secret", repr(result.to_dict()))

    def test_ar_future_valid_fixture(self): self.assertEqual(self.open_assess().ui_security_status, policy.UI_SECURITY_PASS)
    def test_as_pass_not_publication_ready(self): self.assertNotIn("publication", self.open_assess().to_dict())
    def test_at_disclosure_pass_no_gate_unlock(self): self.assertNotIn("gate", self.open_assess().to_dict())
    def test_au_dark_pattern_free_not_lifecycle_resolved(self): self.assertNotIn("lifecycle", self.open_assess().to_dict())
    def test_av_sponsored_setting(self): self.assertTrue(policy.REL_SPONSORED_REQUIRED)
    def test_aw_nofollow_not_inferred(self): self.assertNotIn("nofollow", assess().required_rel_tokens)
    def test_ax_forced_tab_blocked(self): self.assertEqual(self.open_assess(user_initiated_navigation=False).ui_security_status, policy.UI_SECURITY_BLOCKED)
    def test_ay_unknown_pattern_invalid(self): self.assertEqual(self.open_assess(prohibited_patterns=("UNKNOWN",)).ui_security_status, policy.INVALID_INPUT)
    def test_az_generic_open_blocked(self): self.assertEqual(self.open_assess(cta_semantic="OPEN").ui_security_status, policy.UI_SECURITY_BLOCKED)

    def test_ba_unknown_handoff_reason_fails_closed(self):
        value = upstream(True); value["reason_codes"] = ["UNKNOWN_REASON"]
        result = assess(handoff_result=value)
        self.assertEqual((result.ui_security_status, result.render_allowed), (policy.INVALID_INPUT, False))

    def test_bb_known_handoff_reason_remains_valid(self):
        self.assertEqual(self.open_assess().ui_security_status, policy.UI_SECURITY_PASS)

    def test_bc_empty_handoff_reasons_remain_invalid(self):
        value = upstream(True); value["reason_codes"] = []
        self.assertEqual(assess(handoff_result=value).ui_security_status, policy.INVALID_INPUT)


if __name__ == "__main__":
    unittest.main()
