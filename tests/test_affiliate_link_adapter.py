from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_link_adapter as adapter  # noqa: E402
import affiliate_link_policy as policy  # noqa: E402


DUMMY_URL = "https://example.invalid/item?ref=fixture"


def adapt(**changes):
    values = {
        "adapter_version": "0.1",
        "affiliate_url": DUMMY_URL,
        "rights_status": "CONDITIONALLY_APPROVED",
        "publication_context": "WEB_UI",
        "lifecycle_status": "PENDING_OFFICIAL_CONFIRMATION",
        "verification_status": "PASS",
        "publication_gate_overall_eligible": False,
        "pr_disclosure_available": True,
    }
    values.update(changes)
    return adapter.adapt_affiliate_link(**values)


class AffiliateLinkAdapterTests(unittest.TestCase):
    def test_a_version(self): self.assertEqual(adapter.ADAPTER_VERSION, "0.1")
    def test_b_valid_https(self): self.assertEqual(adapt().validation_status, adapter.VALID)
    def test_c_valid_http(self): self.assertEqual(adapt(affiliate_url="http://example.invalid/item").validation_status, adapter.VALID)
    def test_d_javascript_rejected(self): self.assertEqual(adapt(affiliate_url="javascript:alert(1)").validation_status, adapter.INVALID)
    def test_e_data_rejected(self): self.assertEqual(adapt(affiliate_url="data:text/plain,x").validation_status, adapter.INVALID)
    def test_f_file_rejected(self): self.assertEqual(adapt(affiliate_url="file:///tmp/x").validation_status, adapter.INVALID)
    def test_g_ftp_rejected(self): self.assertEqual(adapt(affiliate_url="ftp://example.invalid/x").validation_status, adapter.INVALID)
    def test_h_localhost_rejected(self): self.assertEqual(adapt(affiliate_url="https://localhost/x").validation_status, adapter.INVALID)
    def test_i_subdomain_localhost_rejected(self): self.assertEqual(adapt(affiliate_url="https://x.localhost/x").validation_status, adapter.INVALID)
    def test_j_ipv4_loopback_rejected(self): self.assertEqual(adapt(affiliate_url="https://127.0.0.1/x").validation_status, adapter.INVALID)
    def test_k_ipv6_loopback_rejected(self): self.assertEqual(adapt(affiliate_url="https://[::1]/x").validation_status, adapter.INVALID)
    def test_l_unc_rejected(self): self.assertEqual(adapt(affiliate_url=r"\\server\share").validation_status, adapter.INVALID)
    def test_m_windows_path_rejected(self): self.assertEqual(adapt(affiliate_url="C:/local/file").validation_status, adapter.INVALID)
    def test_n_embedded_username_rejected(self): self.assertEqual(adapt(affiliate_url="https://user@example.invalid/x").validation_status, adapter.INVALID)
    def test_o_embedded_password_rejected(self): self.assertEqual(adapt(affiliate_url="https://user:pass@example.invalid/x").validation_status, adapter.INVALID)
    def test_p_malformed_url(self): self.assertEqual(adapt(affiliate_url="not-a-url").validation_status, adapter.INVALID)
    def test_q_empty_host(self): self.assertEqual(adapt(affiliate_url="https:///path").validation_status, adapter.INVALID)
    def test_r_crlf_rejected(self): self.assertEqual(adapt(affiliate_url="https://example.invalid/x\r\nHeader:x").validation_status, adapter.INVALID)
    def test_s_control_rejected(self): self.assertEqual(adapt(affiliate_url="https://example.invalid/\x01").validation_status, adapter.INVALID)
    def test_t_space_rejected(self): self.assertEqual(adapt(affiliate_url="https://example.invalid/a b").validation_status, adapter.INVALID)
    def test_u_tab_rejected(self): self.assertEqual(adapt(affiliate_url="https://example.invalid/a\tb").validation_status, adapter.INVALID)
    def test_v_gate_closed(self): self.assertFalse(adapt(lifecycle_status="RESOLVED").production_render_allowed)
    def test_w_gate_open_fixture(self): self.assertTrue(adapt(lifecycle_status="RESOLVED", publication_gate_overall_eligible=True).production_render_allowed)
    def test_x_pr_absent_blocks(self): self.assertEqual(adapt(pr_disclosure_available=False).link_status, policy.LINK_BLOCKED)
    def test_y_pr_present(self): self.assertTrue(adapt().pr_disclosure_required)
    def test_z_lifecycle_pending(self): self.assertEqual(adapt().link_status, policy.LINK_PENDING_LIFECYCLE_POLICY)
    def test_aa_no_availability_inference(self): self.assertIn("AVAILABILITY_NOT_INFERRED", adapt().reason_codes)
    def test_ab_no_eligibility_inference(self): self.assertIn("AFFILIATE_ELIGIBILITY_NOT_CONFIRMED", adapt(lifecycle_status="RESOLVED").reason_codes)
    def test_ac_url_not_in_safe_result(self): self.assertNotIn(DUMMY_URL, repr(adapt().to_dict()))
    def test_ad_url_field_not_in_result(self): self.assertNotIn("url", repr(adapt().to_dict()).lower())
    def test_ae_adapter_has_no_logger(self): self.assertFalse(hasattr(adapter, "logger"))

    def test_af_raw_exception_not_returned(self):
        with mock.patch.object(adapter, "_adapt", side_effect=RuntimeError(DUMMY_URL)):
            result = adapt()
        self.assertNotIn(DUMMY_URL, repr(result.to_dict()))

    def test_ag_content_id_extra_rejected(self): self.assertEqual(adapt(content_id="x").validation_status, adapter.INVALID)
    def test_ah_title_extra_rejected(self): self.assertEqual(adapt(title="x").validation_status, adapter.INVALID)
    def test_ai_credential_extra_rejected(self): self.assertEqual(adapt(credential="x").validation_status, adapter.INVALID)
    def test_aj_gate_change_absent(self): self.assertNotIn("gate_unlock", adapt().to_dict())

    def test_ak_policy_result_forwarded_not_recalculated(self):
        fixture = policy.AffiliateLinkResult("0.1", policy.LINK_BLOCKED, False, False, True, False, ("FIXTURE_POLICY_REASON",))
        with mock.patch.object(adapter.link_policy, "assess_affiliate_link", return_value=fixture) as called:
            result = adapt()
        self.assertEqual(result.link_status, policy.LINK_BLOCKED)
        self.assertEqual(called.call_count, 1)
        self.assertIn("FIXTURE_POLICY_REASON", result.reason_codes)

    def test_al_reasons_deterministic(self): self.assertEqual(adapt().reason_codes, tuple(sorted(adapt().reason_codes)))
    def test_am_unknown_version(self): self.assertEqual(adapt(adapter_version="9").validation_status, adapter.INVALID)

    def test_an_internal_exception_safe(self):
        with mock.patch.object(adapter, "_adapt", side_effect=RuntimeError("secret traceback")):
            result = adapt()
        self.assertEqual(result.reason_codes, ("INTERNAL_ADAPTER_ERROR",)); self.assertNotIn("secret", repr(result.to_dict()))

    def test_ao_safe_result_exact_fields(self): self.assertEqual(set(adapt().to_dict()), {"adapter_version", "validation_status", "link_status", "ui_candidate", "production_render_allowed", "pr_disclosure_required", "reason_codes"})
    def test_ap_url_validation_alone_not_render(self): self.assertFalse(adapt().production_render_allowed)
    def test_aq_invalid_port(self): self.assertEqual(adapt(affiliate_url="https://example.invalid:99999/x").validation_status, adapter.INVALID)
    def test_ar_empty_url(self): self.assertEqual(adapt(affiliate_url="").validation_status, adapter.INVALID)
    def test_as_gate_boolean_strict(self): self.assertEqual(adapt(publication_gate_overall_eligible=1).validation_status, adapter.INVALID)
    def test_at_public_json_still_blocked(self): self.assertEqual(adapt(publication_context="PUBLIC_JSON").link_status, policy.LINK_BLOCKED)


if __name__ == "__main__":
    unittest.main()
