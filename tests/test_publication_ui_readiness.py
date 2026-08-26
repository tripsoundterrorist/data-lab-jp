from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import publication_ui_readiness as readiness  # noqa: E402


def components(opened=False):
    policy = {"policy_version": "0.1", "link_status": "LINK_AVAILABLE_FOR_UI" if opened else "LINK_PENDING_LIFECYCLE_POLICY", "ui_candidate": True, "production_render_allowed": opened, "pr_disclosure_required": True, "lifecycle_semantics_resolved": opened, "reason_codes": ["UI_RUNTIME_LINK_CANDIDATE" if opened else "LIFECYCLE_SEMANTICS_PENDING"]}
    adapter = {"adapter_version": "0.1", "validation_status": "VALID", "link_status": policy["link_status"], "ui_candidate": True, "production_render_allowed": opened, "pr_disclosure_required": True, "reason_codes": ["LINK_VALUE_VALIDATED"]}
    handoff = {"handoff_version": "0.1", "render_status": "RENDER_ALLOWED" if opened else "RENDER_BLOCKED", "render_candidate": True, "render_allowed": opened, "pr_disclosure_required": True, "target_context": "WEB_UI", "reason_codes": ["DELEGATED_RENDER_CONDITIONS_SATISFIED" if opened else "ADAPTER_PRODUCTION_RENDER_BLOCKED"]}
    security = {"policy_version": "0.1", "ui_security_status": "UI_SECURITY_PASS" if opened else "BLOCKED_UPSTREAM", "render_allowed": opened, "disclosure_required": True, "external_indicator_required": True, "required_rel_tokens": ["noopener", "noreferrer", "sponsored"], "prohibited_pattern_codes": [], "reason_codes": ["UI_SECURITY_REQUIREMENTS_SATISFIED" if opened else "UPSTREAM_RENDER_BLOCKED"]}
    return policy, adapter, handoff, security


def assess(*, opened=False, gate="CLOSED", lifecycle="PENDING_OFFICIAL_CONFIRMATION", semantics="PENDING_OFFICIAL_CONFIRMATION", version="0.1", values=None, **extra):
    policy, adapter, handoff, security = values or components(opened)
    kwargs = {"readiness_version": version, "affiliate_link_policy_result": policy, "affiliate_link_adapter_result": adapter, "affiliate_ui_handoff_result": handoff, "ui_security_disclosure_result": security, "publication_gate_status": gate, "lifecycle_status": lifecycle, "semantics_status": semantics}
    kwargs.update(extra)
    return readiness.assess_publication_ui_readiness(**kwargs)


class PublicationUIReadinessTests(unittest.TestCase):
    def test_a_version(self): self.assertEqual(readiness.READINESS_VERSION, "0.1")
    def test_b_current_state_blocked(self): self.assertEqual(assess().overall_readiness, readiness.BLOCKED)
    def test_c_all_components_internal_ready(self): self.assertTrue(assess().all_internal_components_ready)
    def test_d_gate_closed_reason(self): self.assertIn("PUBLICATION_GATE_CLOSED", assess().reason_codes)
    def test_e_lifecycle_pending_reason(self): self.assertIn("LIFECYCLE_OFFICIAL_CONFIRMATION_PENDING", assess().reason_codes)
    def test_f_semantics_pending_reason(self): self.assertIn("SEMANTICS_OFFICIAL_CONFIRMATION_PENDING", assess().reason_codes)
    def test_g_all_blockers_unresolved(self): self.assertEqual(len(assess().reason_codes), 3)
    def test_h_internal_ready_not_production(self): self.assertFalse(assess().production_integration_allowed)
    def test_i_future_all_open(self): self.assertEqual(assess(opened=True, gate="PASS", lifecycle="RESOLVED", semantics="RESOLVED").overall_readiness, readiness.PRODUCTION_CANDIDATE)

    def altered(self, index, key, value):
        values = list(components()); values[index] = deepcopy(values[index]); values[index][key] = value
        return assess(values=tuple(values))

    def test_j_policy_unknown_version(self): self.assertEqual(self.altered(0, "policy_version", "9").overall_readiness, readiness.INVALID_INPUT)
    def test_k_adapter_unknown_version(self): self.assertEqual(self.altered(1, "adapter_version", "9").overall_readiness, readiness.INVALID_INPUT)
    def test_l_handoff_unknown_version(self): self.assertEqual(self.altered(2, "handoff_version", "9").overall_readiness, readiness.INVALID_INPUT)
    def test_m_security_unknown_version(self): self.assertEqual(self.altered(3, "policy_version", "9").overall_readiness, readiness.INVALID_INPUT)
    def test_n_malformed_policy(self): self.assertEqual(assess(values=([], *components()[1:])).overall_readiness, readiness.INVALID_INPUT)
    def test_o_malformed_adapter(self): self.assertEqual(assess(values=(components()[0], [], *components()[2:])).overall_readiness, readiness.INVALID_INPUT)
    def test_p_malformed_handoff(self): self.assertEqual(assess(values=(*components()[:2], [], components()[3])).overall_readiness, readiness.INVALID_INPUT)
    def test_q_malformed_security(self): self.assertEqual(assess(values=(*components()[:3], [])).overall_readiness, readiness.INVALID_INPUT)

    def test_r_policy_adapter_contradiction(self):
        values = list(components()); values[0] = deepcopy(values[0]); values[0]["link_status"] = "LINK_BLOCKED"
        self.assertEqual(assess(values=tuple(values)).overall_readiness, readiness.MANUAL_REVIEW_REQUIRED)

    def test_s_adapter_handoff_contradiction(self):
        values = list(components()); values[2] = deepcopy(values[2]); values[2]["render_allowed"] = True; values[2]["render_status"] = "RENDER_ALLOWED"
        self.assertEqual(assess(values=tuple(values)).overall_readiness, readiness.MANUAL_REVIEW_REQUIRED)

    def test_t_handoff_security_contradiction(self):
        values = list(components()); values[3] = deepcopy(values[3]); values[3]["render_allowed"] = True; values[3]["ui_security_status"] = "UI_SECURITY_PASS"
        self.assertEqual(assess(values=tuple(values)).overall_readiness, readiness.MANUAL_REVIEW_REQUIRED)

    def test_u_security_pass_cannot_bypass_gate(self): self.assertEqual(assess(opened=True).overall_readiness, readiness.MANUAL_REVIEW_REQUIRED)
    def test_v_pr_preserved(self): self.assertEqual(self.altered(1, "pr_disclosure_required", False).overall_readiness, readiness.INVALID_INPUT)
    def test_w_public_json_prohibition_module_boundary(self): self.assertNotIn("public_json", assess().to_dict())
    def test_x_lifecycle_inference_absent(self): self.assertEqual(assess().lifecycle_status, "PENDING_OFFICIAL_CONFIRMATION")
    def test_y_semantics_inference_absent(self): self.assertEqual(assess().semantics_status, "PENDING_OFFICIAL_CONFIRMATION")
    def test_z_url_absent_input_contract(self): self.assertNotIn("url", readiness.assess_publication_ui_readiness.__annotations__)
    def test_aa_url_absent_output(self): self.assertNotIn("url", repr(assess().to_dict()).lower())

    def injected(self, component, key):
        values = list(components()); values[component] = deepcopy(values[component]); values[component][key] = "x"
        return assess(values=tuple(values))

    def test_ab_title_rejected(self): self.assertEqual(self.injected(0, "title").overall_readiness, readiness.INVALID_INPUT)
    def test_ac_content_id_rejected(self): self.assertEqual(self.injected(1, "content_id").overall_readiness, readiness.INVALID_INPUT)
    def test_ad_product_id_rejected(self): self.assertEqual(self.injected(2, "product_id").overall_readiness, readiness.INVALID_INPUT)
    def test_ae_affiliate_id_rejected(self): self.assertEqual(self.injected(3, "affiliate_id").overall_readiness, readiness.INVALID_INPUT)
    def test_af_credential_rejected(self): self.assertEqual(self.injected(0, "credential").overall_readiness, readiness.INVALID_INPUT)
    def test_ag_path_rejected(self): self.assertEqual(self.injected(1, "absolute_path").overall_readiness, readiness.INVALID_INPUT)
    def test_ah_raw_exception_rejected(self): self.assertEqual(self.injected(2, "raw_exception").overall_readiness, readiness.INVALID_INPUT)
    def test_ai_safe_output_allowlist(self): self.assertEqual(set(assess().to_dict()), {"readiness_version", "overall_readiness", "all_internal_components_ready", "production_integration_allowed", "publication_gate_status", "lifecycle_status", "semantics_status", "component_statuses", "reason_codes"})
    def test_aj_reasons_deterministic(self): self.assertEqual(assess().reason_codes, tuple(sorted(assess().reason_codes)))
    def test_ak_gate_not_mutated(self): self.assertEqual(assess().publication_gate_status, "CLOSED")
    def test_al_lifecycle_not_mutated(self): self.assertEqual(assess().lifecycle_status, "PENDING_OFFICIAL_CONFIRMATION")
    def test_am_semantics_not_mutated(self): self.assertEqual(assess().semantics_status, "PENDING_OFFICIAL_CONFIRMATION")
    def test_an_blocker_mutation_absent(self): self.assertNotIn("blocker", assess().to_dict())
    def test_ao_publication_status_absent(self): self.assertNotIn("publication_status", assess().to_dict())

    def test_ap_internal_exception_safe(self):
        with mock.patch.object(readiness, "_assess", side_effect=RuntimeError("secret traceback")):
            result = assess()
        self.assertEqual(result.reason_codes, ("INTERNAL_READINESS_ERROR",)); self.assertNotIn("secret", repr(result.to_dict()))

    def test_aq_future_open_candidate(self): self.assertTrue(assess(opened=True, gate="PASS", lifecycle="RESOLVED", semantics="RESOLVED").production_integration_allowed)
    def test_ar_candidate_not_deploy_approved(self): self.assertIn("DEPLOY_APPROVAL_REQUIRED", assess(opened=True, gate="PASS", lifecycle="RESOLVED", semantics="RESOLVED").reason_codes)
    def test_as_component_flag_deterministic(self): self.assertEqual(assess().all_internal_components_ready, assess().all_internal_components_ready)
    def test_at_contradiction_manual_review(self): self.assertEqual(self.altered(1, "production_render_allowed", True).overall_readiness, readiness.MANUAL_REVIEW_REQUIRED)
    def test_au_unknown_readiness_version(self): self.assertEqual(assess(version="9").overall_readiness, readiness.INVALID_INPUT)
    def test_av_unknown_gate(self): self.assertEqual(assess(gate="UNKNOWN").overall_readiness, readiness.INVALID_INPUT)
    def test_aw_unknown_lifecycle(self): self.assertEqual(assess(lifecycle="UNKNOWN").overall_readiness, readiness.INVALID_INPUT)
    def test_ax_unknown_semantics(self): self.assertEqual(assess(semantics="UNKNOWN").overall_readiness, readiness.INVALID_INPUT)
    def test_ay_component_status_names(self): self.assertEqual(set(assess().to_dict()["component_statuses"]), set(readiness.COMPONENT_NAMES))
    def test_az_extra_top_level_rejected(self): self.assertEqual(assess(unexpected=True).overall_readiness, readiness.INVALID_INPUT)

    def assert_component_fail_closed(self, index, key, value):
        result = self.altered(index, key, value)
        self.assertEqual(result.overall_readiness, readiness.INVALID_INPUT)
        self.assertFalse(result.production_integration_allowed)
        self.assertFalse(result.all_internal_components_ready)
        self.assertNotEqual(result.overall_readiness, readiness.PRODUCTION_CANDIDATE)

    def test_ba_unknown_policy_link_status(self): self.assert_component_fail_closed(0, "link_status", "UNKNOWN_LINK_STATUS")
    def test_bb_unknown_adapter_validation_status(self): self.assert_component_fail_closed(1, "validation_status", "UNKNOWN_VALIDATION_STATUS")
    def test_bc_unknown_adapter_link_status(self): self.assert_component_fail_closed(1, "link_status", "UNKNOWN_LINK_STATUS")
    def test_bd_unknown_handoff_render_status(self): self.assert_component_fail_closed(2, "render_status", "UNKNOWN_RENDER_STATUS")
    def test_be_unknown_security_status(self): self.assert_component_fail_closed(3, "ui_security_status", "UNKNOWN_SECURITY_STATUS")

    def unknown_reason(self, index):
        values = list(components(True)); values[index] = deepcopy(values[index]); values[index]["reason_codes"] = ["UNKNOWN_REASON"]
        return assess(values=tuple(values), gate="PASS", lifecycle="RESOLVED", semantics="RESOLVED")

    def test_bf_unknown_policy_reason(self): self.assertEqual(self.unknown_reason(0).overall_readiness, readiness.INVALID_INPUT)
    def test_bg_unknown_adapter_reason(self): self.assertEqual(self.unknown_reason(1).overall_readiness, readiness.INVALID_INPUT)
    def test_bh_unknown_handoff_reason(self): self.assertEqual(self.unknown_reason(2).overall_readiness, readiness.INVALID_INPUT)
    def test_bi_unknown_security_reason(self): self.assertEqual(self.unknown_reason(3).overall_readiness, readiness.INVALID_INPUT)

    def test_bj_unknown_reason_open_fixture_not_allowed(self):
        result = self.unknown_reason(3)
        self.assertFalse(result.production_integration_allowed)
        self.assertNotEqual(result.overall_readiness, readiness.PRODUCTION_CANDIDATE)

    def test_bk_known_reasons_open_fixture_still_candidate(self):
        result = assess(opened=True, gate="PASS", lifecycle="RESOLVED", semantics="RESOLVED")
        self.assertEqual(result.overall_readiness, readiness.PRODUCTION_CANDIDATE)
        self.assertTrue(result.production_integration_allowed)

    def test_bl_empty_reasons_remain_invalid(self):
        values = list(components()); values[0] = deepcopy(values[0]); values[0]["reason_codes"] = []
        self.assertEqual(assess(values=tuple(values)).overall_readiness, readiness.INVALID_INPUT)

    def test_bm_blocked_status_with_candidate_requires_review(self):
        self.assertEqual(self.altered(0, "link_status", "LINK_BLOCKED").overall_readiness, readiness.MANUAL_REVIEW_REQUIRED)

    def test_bn_adapter_blocked_with_render_flag_rejected(self):
        values = list(components()); values[1] = deepcopy(values[1]); values[1]["link_status"] = "LINK_BLOCKED"; values[1]["production_render_allowed"] = True
        result = assess(values=tuple(values))
        self.assertEqual(result.overall_readiness, readiness.INVALID_INPUT)

    def test_bo_handoff_blocked_with_allowed_rejected(self):
        values = list(components()); values[2] = deepcopy(values[2]); values[2]["render_allowed"] = True
        self.assertEqual(assess(values=tuple(values)).overall_readiness, readiness.INVALID_INPUT)

    def test_bp_security_blocked_with_allowed_rejected(self):
        values = list(components()); values[3] = deepcopy(values[3]); values[3]["render_allowed"] = True
        self.assertEqual(assess(values=tuple(values)).overall_readiness, readiness.INVALID_INPUT)

    def test_bq_unknown_status_open_fixture_not_allowed(self):
        values = list(components(True)); values[0] = deepcopy(values[0]); values[0]["link_status"] = "UNKNOWN_LINK_STATUS"
        result = assess(values=tuple(values), gate="PASS", lifecycle="RESOLVED", semantics="RESOLVED")
        self.assertEqual(result.overall_readiness, readiness.INVALID_INPUT)
        self.assertFalse(result.production_integration_allowed)


if __name__ == "__main__":
    unittest.main()
