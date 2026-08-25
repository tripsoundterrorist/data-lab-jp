from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_ui_handoff as handoff  # noqa: E402


def adapter_result(*, candidate=True, production=False):
    return {
        "adapter_version": "0.1",
        "validation_status": "VALID",
        "link_status": "LINK_AVAILABLE_FOR_UI" if production else "LINK_PENDING_LIFECYCLE_POLICY",
        "ui_candidate": candidate,
        "production_render_allowed": production,
        "pr_disclosure_required": True,
        "reason_codes": ["LINK_VALUE_VALIDATED", "LIFECYCLE_SEMANTICS_PENDING"] if not production else ["LINK_VALUE_VALIDATED", "UI_RUNTIME_LINK_CANDIDATE"],
    }


def build(*, result=None, context="WEB_UI", disclosure=True, version="0.1", **extra):
    values = {
        "handoff_version": version,
        "adapter_result": adapter_result() if result is None else result,
        "target_context": context,
        "disclosure_available": disclosure,
    }
    values.update(extra)
    return handoff.build_ui_handoff(**values)


class AffiliateUIHandoffTests(unittest.TestCase):
    def test_a_version(self): self.assertEqual(handoff.HANDOFF_VERSION, "0.1")
    def test_b_current_gate_closed_blocked(self): self.assertEqual(build().render_status, handoff.RENDER_BLOCKED)
    def test_c_valid_ui_candidate(self): self.assertTrue(build().render_candidate)
    def test_d_ui_candidate_false(self): self.assertFalse(build(result=adapter_result(candidate=False)).render_candidate)
    def test_e_production_false(self): self.assertFalse(build().render_allowed)
    def test_f_future_gate_open_fixture(self): self.assertEqual(build(result=adapter_result(production=True)).render_status, handoff.RENDER_ALLOWED)
    def test_g_pr_required(self): self.assertTrue(build().pr_disclosure_required)
    def test_h_pr_unavailable_block(self): self.assertEqual(build(disclosure=False).render_status, handoff.RENDER_BLOCKED)
    def test_i_public_json_reject(self): self.assertEqual(build(context="PUBLIC_JSON").render_status, handoff.RENDER_BLOCKED)
    def test_j_public_data_reject(self): self.assertEqual(build(context="PUBLIC_DATA").render_status, handoff.RENDER_BLOCKED)
    def test_k_static_export_reject(self): self.assertEqual(build(context="STATIC_EXPORT").render_status, handoff.RENDER_BLOCKED)
    def test_l_api_export_reject(self): self.assertEqual(build(context="API_RESPONSE_EXPORT").render_status, handoff.RENDER_BLOCKED)
    def test_m_unknown_context(self): self.assertEqual(build(context="EMAIL").render_status, handoff.INVALID_INPUT)

    def test_n_unknown_adapter_version(self):
        value = adapter_result(); value["adapter_version"] = "9"
        self.assertEqual(build(result=value).render_status, handoff.INVALID_INPUT)

    def test_o_malformed_result(self): self.assertEqual(build(result=[]).render_status, handoff.INVALID_INPUT)

    def injected(self, key, value="x"):
        result = adapter_result(); result[key] = value
        return build(result=result)

    def test_p_unknown_field(self): self.assertEqual(self.injected("extra").render_status, handoff.INVALID_INPUT)
    def test_q_affiliate_url_reject(self): self.assertEqual(self.injected("affiliate_url", "fixture").render_status, handoff.INVALID_INPUT)
    def test_r_product_url_reject(self): self.assertEqual(self.injected("product_url").render_status, handoff.INVALID_INPUT)
    def test_s_content_id_reject(self): self.assertEqual(self.injected("content_id").render_status, handoff.INVALID_INPUT)
    def test_t_product_id_reject(self): self.assertEqual(self.injected("product_id").render_status, handoff.INVALID_INPUT)
    def test_u_title_reject(self): self.assertEqual(self.injected("title").render_status, handoff.INVALID_INPUT)
    def test_v_credential_reject(self): self.assertEqual(self.injected("credential").render_status, handoff.INVALID_INPUT)
    def test_w_path_reject(self): self.assertEqual(self.injected("absolute_path").render_status, handoff.INVALID_INPUT)
    def test_x_raw_exception_reject(self): self.assertEqual(self.injected("raw_exception").render_status, handoff.INVALID_INPUT)

    def test_y_contradictory_flags(self):
        value = adapter_result(candidate=False, production=True)
        self.assertEqual(build(result=value).render_status, handoff.INVALID_INPUT)

    def test_z_render_cannot_bypass_adapter(self): self.assertFalse(build().render_allowed)
    def test_aa_gate_mutation_absent(self): self.assertNotIn("gate", build().to_dict())
    def test_ab_lifecycle_mutation_absent(self): self.assertNotIn("lifecycle", build().to_dict())
    def test_ac_availability_absent(self): self.assertNotIn("availability", repr(build().to_dict()).lower())
    def test_ad_eligibility_absent(self): self.assertNotIn("eligibility", repr(build().to_dict()).lower())
    def test_ae_purchasability_absent(self): self.assertNotIn("purchas", repr(build().to_dict()).lower())
    def test_af_safe_output_allowlist(self): self.assertEqual(set(build().to_dict()), {"handoff_version", "render_status", "render_candidate", "render_allowed", "pr_disclosure_required", "target_context", "reason_codes"})
    def test_ag_deterministic_reasons(self): self.assertEqual(build().reason_codes, tuple(sorted(build().reason_codes)))

    def test_ah_internal_exception_safe(self):
        with mock.patch.object(handoff, "_handoff", side_effect=RuntimeError("secret traceback")):
            result = build()
        self.assertEqual(result.reason_codes, ("INTERNAL_HANDOFF_ERROR",)); self.assertNotIn("secret", repr(result.to_dict()))

    def test_ai_candidate_differs_allowed(self): self.assertEqual((build().render_candidate, build().render_allowed), (True, False))
    def test_aj_current_state_deterministic(self): self.assertEqual(build().to_dict(), build().to_dict())
    def test_ak_unknown_handoff_version(self): self.assertEqual(build(version="9").render_status, handoff.INVALID_INPUT)

    def test_al_unknown_reason(self):
        value = adapter_result(); value["reason_codes"] = ["UNKNOWN_REASON"]
        self.assertEqual(build(result=value).render_status, handoff.INVALID_INPUT)

    def test_am_empty_reasons(self):
        value = adapter_result(); value["reason_codes"] = []
        self.assertEqual(build(result=value).render_status, handoff.INVALID_INPUT)

    def test_an_pr_requirement_contradiction(self):
        value = adapter_result(); value["pr_disclosure_required"] = False
        self.assertEqual(build(result=value).render_status, handoff.INVALID_INPUT)

    def test_ao_disclosure_flag_strict(self): self.assertEqual(build(disclosure=1).render_status, handoff.INVALID_INPUT)
    def test_ap_extra_top_level_rejected(self): self.assertEqual(build(unexpected=True).render_status, handoff.INVALID_INPUT)
    def test_aq_output_contains_no_adapter_reasons(self): self.assertNotIn("LIFECYCLE_SEMANTICS_PENDING", build().reason_codes)
    def test_ar_render_allowed_boolean(self): self.assertIs(build(result=adapter_result(production=True)).render_allowed, True)
    def test_as_blocked_context_never_candidate(self): self.assertFalse(build(context="PUBLIC_JSON").render_candidate)
    def test_at_no_url_word_in_output(self): self.assertNotIn("url", repr(build().to_dict()).lower())


if __name__ == "__main__":
    unittest.main()
