from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import official_blocker_policy as policy  # noqa: E402


class OfficialBlockerPolicyTests(unittest.TestCase):
    def test_a_lifecycle_pending(self): self.assertEqual(policy.blocker_for(policy.LIFECYCLE_BLOCKER).status, policy.PENDING_OFFICIAL_CONFIRMATION)
    def test_b_lifecycle_unlock_false(self): self.assertFalse(policy.blocker_for(policy.LIFECYCLE_BLOCKER).gate_unlock_allowed)
    def test_c_sort_pending(self): self.assertEqual(policy.blocker_for(policy.SORT_BLOCKER).status, policy.PENDING_OFFICIAL_CONFIRMATION)
    def test_d_sort_unlock_false(self): self.assertFalse(policy.blocker_for(policy.SORT_BLOCKER).gate_unlock_allowed)
    def test_e_publication_internal_approval(self): self.assertEqual(policy.blocker_for(policy.PUBLICATION_BLOCKER).status, policy.INTERNAL_APPROVAL_REQUIRED)
    def test_f_zero_result_inference_forbidden(self): self.assertFalse(policy.inference_allowed("ZERO_RESULT_MEANS_SALE_ENDED"))
    def test_g_affiliate_absence_inference_forbidden(self): self.assertFalse(policy.inference_allowed("AFFILIATE_URL_ABSENT_MEANS_INELIGIBLE"))
    def test_h_api_visible_inference_forbidden(self): self.assertFalse(policy.inference_allowed("API_VISIBLE_MEANS_PURCHASABLE"))
    def test_i_api_invisible_inference_forbidden(self): self.assertFalse(policy.inference_allowed("API_INVISIBLE_MEANS_DELETED"))
    def test_j_stale_observation_inference_forbidden(self): self.assertFalse(policy.inference_allowed("NOT_OBSERVED_FOR_DAYS_MEANS_UNAVAILABLE"))
    def test_k_rank_semantics_unconfirmed(self): self.assertIn("official sort=rank definition", policy.blocker_for(policy.SORT_BLOCKER).unresolved_questions)
    def test_l_review_semantics_unconfirmed(self): self.assertIn("official sort=review definition", policy.blocker_for(policy.SORT_BLOCKER).unresolved_questions)
    def test_m_rank_only_resolved_not_enough(self): self.assertFalse(policy.semantics_gate_unlock_allowed(policy.RESOLVED, policy.PENDING_OFFICIAL_CONFIRMATION, policy.DIRECT_SUPPORT_CONFIRMATION))
    def test_n_review_only_resolved_not_enough(self): self.assertFalse(policy.semantics_gate_unlock_allowed(policy.PENDING_OFFICIAL_CONFIRMATION, policy.RESOLVED, policy.DIRECT_SUPPORT_CONFIRMATION))
    def test_o_third_party_evidence_cannot_resolve(self): self.assertFalse(policy.semantics_gate_unlock_allowed(policy.RESOLVED, policy.RESOLVED, "THIRD_PARTY_BLOG"))
    def test_p_official_support_evidence_allowed(self): self.assertTrue(policy.semantics_gate_unlock_allowed(policy.RESOLVED, policy.RESOLVED, policy.DIRECT_SUPPORT_CONFIRMATION))
    def test_q_official_docs_evidence_allowed(self): self.assertTrue(policy.semantics_gate_unlock_allowed(policy.RESOLVED, policy.RESOLVED, policy.OFFICIAL_DOCUMENTATION))
    def test_r_partial_resolution_safe(self):
        record = replace(policy.blocker_for(policy.LIFECYCLE_BLOCKER), status=policy.PARTIALLY_RESOLVED, evidence_type=policy.DIRECT_SUPPORT_CONFIRMATION); self.assertFalse(policy.resolution_unlock_allowed(record))
    def test_s_unknown_blocker_fails_closed(self):
        with self.assertRaisesRegex(KeyError, "UNKNOWN_BLOCKER"): policy.blocker_for("UNKNOWN")
    def test_t_unknown_inference_fails_closed(self):
        with self.assertRaisesRegex(KeyError, "UNKNOWN_INFERENCE"): policy.inference_allowed("UNKNOWN")
    def test_u_unknown_state_fails_closed(self):
        record = replace(policy.blocker_for(policy.LIFECYCLE_BLOCKER), status="UNKNOWN", gate_unlock_allowed=True, unresolved_questions=()); self.assertFalse(policy.resolution_unlock_allowed(record))
    def test_v_invalid_unlock_true_rejected_while_pending(self):
        record = replace(policy.blocker_for(policy.LIFECYCLE_BLOCKER), gate_unlock_allowed=True); self.assertFalse(policy.resolution_unlock_allowed(record))
    def test_w_publication_activation_auto_unlock_forbidden(self):
        record = replace(policy.blocker_for(policy.PUBLICATION_BLOCKER), status=policy.RESOLVED, gate_unlock_allowed=True); self.assertFalse(policy.resolution_unlock_allowed(record))
    def test_x_rights_pass_alone_cannot_activate(self): self.assertFalse(policy.publication_activation_allowed({"RIGHTS_GATE": "PASS"}, explicit_internal_approval=True))
    def test_y_blocker_ids_deterministic(self): self.assertEqual(tuple(policy.BLOCKERS), policy.BLOCKER_IDS)
    def test_z_policy_version_fixed(self): self.assertEqual((policy.POLICY_VERSION, policy.BLOCKER_VERSION), ("0.1", "0.1"))
    def test_aa_safe_result_has_no_secret_or_path(self):
        result = json.dumps(policy.safe_registry_result()).lower(); self.assertNotIn("api_id=", result); self.assertNotIn("c:\\\\", result); self.assertNotIn("/users/", result)
    def test_ab_raw_email_not_in_safe_result(self):
        result = json.dumps(policy.safe_registry_result()); self.assertNotIn("email_body", result); self.assertNotIn("unresolved_questions", result)
    def test_ac_lifecycle_resolved_requires_no_open_questions(self):
        record = replace(policy.blocker_for(policy.LIFECYCLE_BLOCKER), status=policy.RESOLVED, evidence_type=policy.DIRECT_SUPPORT_CONFIRMATION, gate_unlock_allowed=True); self.assertFalse(policy.resolution_unlock_allowed(record))
    def test_ad_lifecycle_official_complete_can_unlock_proposal(self):
        record = replace(policy.blocker_for(policy.LIFECYCLE_BLOCKER), status=policy.RESOLVED, evidence_type=policy.DIRECT_SUPPORT_CONFIRMATION, unresolved_questions=(), gate_unlock_allowed=True, evidence_reference="support-case-2026-001"); self.assertTrue(policy.resolution_unlock_allowed(record))
    def test_ae_internal_validation_cannot_resolve_official_blocker(self):
        record = replace(policy.blocker_for(policy.LIFECYCLE_BLOCKER), status=policy.RESOLVED, evidence_type=policy.INTERNAL_VALIDATION, unresolved_questions=(), gate_unlock_allowed=True); self.assertFalse(policy.resolution_unlock_allowed(record))
    def test_af_unsafe_evidence_reference_rejected(self):
        record = replace(policy.blocker_for(policy.LIFECYCLE_BLOCKER), status=policy.RESOLVED, evidence_type=policy.DIRECT_SUPPORT_CONFIRMATION, unresolved_questions=(), gate_unlock_allowed=True, evidence_reference="C:\\Users\\secret.txt"); self.assertFalse(policy.resolution_unlock_allowed(record))
    def test_ag_multiline_evidence_reference_rejected(self): self.assertFalse(policy.evidence_reference_is_safe("line1\nline2"))
    def test_ah_registry_self_validation(self): self.assertEqual(policy.validate_registry(), ())
    def test_ai_current_safe_result_unlocks_none(self): self.assertTrue(all(not row["gate_unlock_allowed"] for row in policy.safe_registry_result()["blockers"]))
    def test_aj_publication_requires_all_prerequisites(self):
        gates = {name: "PASS" for name in ("RIGHTS_GATE", "LIFECYCLE_GATE", "SEMANTICS_GATE", "DATA_POLICY_GATE", "ARTIFACT_VALIDATION", "PRODUCTION_BUILD", "DEPLOYMENT_PREFLIGHT")}; self.assertTrue(policy.publication_activation_allowed(gates, explicit_internal_approval=True)); gates["LIFECYCLE_GATE"]="PENDING"; self.assertFalse(policy.publication_activation_allowed(gates, explicit_internal_approval=True))
    def test_ak_publication_requires_explicit_approval(self):
        gates = {name: "PASS" for name in ("RIGHTS_GATE", "LIFECYCLE_GATE", "SEMANTICS_GATE", "DATA_POLICY_GATE", "ARTIFACT_VALIDATION", "PRODUCTION_BUILD", "DEPLOYMENT_PREFLIGHT")}; self.assertFalse(policy.publication_activation_allowed(gates, explicit_internal_approval=False))


if __name__ == "__main__": unittest.main()
