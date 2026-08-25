from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import publication_readiness as readiness  # noqa: E402
from official_blocker_policy import (  # noqa: E402
    BLOCKER_IDS, INTERNAL_APPROVAL_REQUIRED, PENDING_OFFICIAL_CONFIRMATION,
    RESOLVED,
)
from publication_gate import CLOSED, PASS  # noqa: E402

NOW = datetime(2026, 8, 26, 0, 0, tzinfo=timezone.utc)


def current(): return readiness.current_input()
def report(value=None): return readiness.build_report(value or current(), generated_at=NOW)
def changed(value, **kwargs): return replace(value, **kwargs)
def all_ready():
    value = current()
    return changed(
        value, gates={name: PASS for name in value.gates}, publication_status="public",
        overall_eligible=True, blockers={name: RESOLVED for name in BLOCKER_IDS},
    )


class PublicationReadinessTests(unittest.TestCase):
    def test_a_current_state_blocked(self): self.assertEqual(report().overall_readiness, readiness.BLOCKED)
    def test_b_rights_pass_displayed(self): self.assertIn({"gate": "RIGHTS_GATE", "status": PASS}, report().gate_summaries)
    def test_c_data_policy_pass_displayed(self): self.assertIn({"gate": "DATA_POLICY_GATE", "status": PASS}, report().gate_summaries)
    def test_d_lifecycle_pending_displayed(self): self.assertIn({"gate": "LIFECYCLE_GATE", "status": PENDING_OFFICIAL_CONFIRMATION}, report().gate_summaries)
    def test_e_semantics_pending_displayed(self): self.assertIn({"gate": "SEMANTICS_GATE", "status": PENDING_OFFICIAL_CONFIRMATION}, report().gate_summaries)
    def test_f_publication_status_closed_displayed(self): self.assertIn({"gate": "PUBLICATION_STATUS_GATE", "status": CLOSED}, report().gate_summaries)
    def test_g_overall_eligible_false(self): self.assertFalse(report().overall_eligible)
    def test_h_lifecycle_blocker_displayed(self): self.assertEqual(report().blocker_summaries[0]["blocker_id"], "DMM_LIFECYCLE_AVAILABILITY")
    def test_i_sort_blocker_displayed(self): self.assertEqual(report().blocker_summaries[1]["blocker_id"], "DMM_SORT_SEMANTICS")
    def test_j_activation_blocker_displayed(self): self.assertEqual(report().blocker_summaries[2]["status"], INTERNAL_APPROVAL_REQUIRED)
    def test_k_rights_pass_alone_not_ready(self): self.assertEqual(report().overall_readiness, readiness.BLOCKED)
    def test_l_temporal_comparison_not_ready(self):
        value = changed(current(), temporal_observation={"day1_baseline_exists": True, "day2_comparison_exists": True, "history_count": 2, "production_readiness": readiness.NOT_EVALUATED}); self.assertFalse(report(value).overall_eligible)
    def test_m_history_one_not_production_judgment(self): self.assertEqual(report().temporal_observational_summary["production_readiness"], readiness.NOT_EVALUATED)
    def test_n_all_official_pending_blocked(self): self.assertEqual(report().overall_readiness, readiness.BLOCKED)
    def test_o_lifecycle_resolved_only_not_ready(self):
        value=current(); blockers=dict(value.blockers); blockers["DMM_LIFECYCLE_AVAILABILITY"]=RESOLVED; gates=dict(value.gates); gates["LIFECYCLE_GATE"]=PASS; self.assertEqual(report(changed(value,blockers=blockers,gates=gates)).overall_readiness,readiness.BLOCKED)
    def test_p_semantics_resolved_only_not_ready(self):
        value=current(); blockers=dict(value.blockers); blockers["DMM_SORT_SEMANTICS"]=RESOLVED; gates=dict(value.gates); gates["SEMANTICS_GATE"]=PASS; self.assertEqual(report(changed(value,blockers=blockers,gates=gates)).overall_readiness,readiness.BLOCKED)
    def test_q_official_resolved_activation_pending_not_ready(self):
        value=current(); blockers=dict(value.blockers); blockers["DMM_LIFECYCLE_AVAILABILITY"]=blockers["DMM_SORT_SEMANTICS"]=RESOLVED; gates=dict(value.gates); gates["LIFECYCLE_GATE"]=gates["SEMANTICS_GATE"]=PASS; self.assertEqual(report(changed(value,blockers=blockers,gates=gates)).overall_readiness,readiness.BLOCKED)
    def test_r_local_status_not_ready(self): self.assertEqual(report().overall_readiness, readiness.BLOCKED)
    def test_s_all_required_conditions_ready(self): self.assertEqual(report(all_ready()).overall_readiness, readiness.READY)
    def test_t_contradictory_gate_state_fail_closed(self): self.assertEqual(report(changed(current(), overall_eligible=True)).overall_readiness, readiness.FAIL_CLOSED)
    def test_u_unknown_blocker_fail_closed(self): self.assertEqual(report(changed(current(), blockers={"UNKNOWN": "RESOLVED"})).overall_readiness, readiness.FAIL_CLOSED)
    def test_v_unknown_version_fail_closed(self): self.assertEqual(report(changed(current(), gate_version="9.9")).overall_readiness, readiness.FAIL_CLOSED)
    def test_w_secret_leak_rejected(self): self.assertEqual(report(changed(current(), temporal_observation={"api_id": "fixture"})).overall_readiness, readiness.FAIL_CLOSED)
    def test_x_raw_email_leak_rejected(self): self.assertEqual(report(changed(current(), temporal_observation={"raw_support_email": "body"})).overall_readiness, readiness.FAIL_CLOSED)
    def test_y_absolute_path_leak_rejected(self): self.assertEqual(report(changed(current(), temporal_observation={"note": "C:\\Users\\name\\file"})).overall_readiness, readiness.FAIL_CLOSED)
    def test_z_content_id_leak_rejected(self): self.assertEqual(report(changed(current(), temporal_observation={"content_id": "cid"})).overall_readiness, readiness.FAIL_CLOSED)
    def test_aa_anonymous_id_leak_rejected(self): self.assertEqual(report(changed(current(), temporal_observation={"anonymous_item_ids": []})).overall_readiness, readiness.FAIL_CLOSED)
    def test_ab_next_actions_deterministic(self): self.assertEqual(report().next_actions, readiness.NEXT_ACTION_ORDER)
    def test_ac_no_automatic_activation(self): self.assertFalse(report().overall_eligible)
    def test_ad_generated_at_timezone(self): self.assertTrue(report().generated_at.endswith("+00:00"))
    def test_ae_internal_exception_safe_result(self):
        class Exploding(dict):
            def items(self): raise RuntimeError("fixture")
        self.assertEqual(report(changed(current(), temporal_observation=Exploding())).overall_readiness, readiness.FAIL_CLOSED)
    def test_af_unknown_gate_fail_closed(self): self.assertEqual(report(changed(current(), gates={"UNKNOWN": PASS})).overall_readiness, readiness.FAIL_CLOSED)
    def test_ag_unknown_gate_status_fail_closed(self):
        gates=dict(current().gates);gates["RIGHTS_GATE"]="UNKNOWN";self.assertEqual(report(changed(current(),gates=gates)).overall_readiness,readiness.FAIL_CLOSED)
    def test_ah_public_with_unresolved_activation_fail_closed(self): self.assertEqual(report(changed(current(),publication_status="public")).overall_readiness,readiness.FAIL_CLOSED)
    def test_ai_malformed_input_fail_closed(self): self.assertEqual(readiness.build_report({},generated_at=NOW).overall_readiness,readiness.FAIL_CLOSED)
    def test_aj_naive_generated_at_fail_closed(self): self.assertEqual(readiness.build_report(current(),generated_at=datetime(2026,8,26)).overall_readiness,readiness.FAIL_CLOSED)
    def test_ak_rights_summary_has_approved_fields(self): self.assertIn("title",report().rights_summary["fields"]["APPROVED"])
    def test_al_rights_summary_redacts_secret_names(self):
        text=json.dumps(report().rights_summary);self.assertNotIn("api_id",text);self.assertNotIn("affiliate_id",text);self.assertEqual(report().rights_summary["secret_field_names_redacted"],2)
    def test_am_lifecycle_unresolved_summary(self): self.assertIn("API_ZERO_RESULT_SEMANTICS_UNRESOLVED",report().lifecycle_summary)
    def test_an_semantics_unresolved_summary(self): self.assertIn("RANK_SORT_OFFICIAL_DEFINITION_UNRESOLVED",report().semantics_summary)
    def test_ao_temporal_is_observational_only(self): self.assertEqual(report().temporal_observational_summary["interpretation"],"OBSERVATIONAL_ONLY")
    def test_ap_safe_output_has_no_forbidden_payload(self):
        text=json.dumps(report().to_dict()).lower();self.assertNotIn("raw_support_email",text);self.assertNotIn("content_id",text);self.assertNotIn("anonymous_item_ids",text);self.assertNotIn("traceback",text)
    def test_aq_report_version_fixed(self): self.assertEqual(readiness.REPORT_VERSION,"0.1")
    def test_ar_reason_codes_deterministic(self): self.assertEqual(report().reason_codes,report().reason_codes)
    def test_as_temporal_production_claim_rejected(self):
        temporal=dict(current().temporal_observation);temporal["production_readiness"]="READY";self.assertEqual(report(changed(current(),temporal_observation=temporal)).overall_readiness,readiness.FAIL_CLOSED)


if __name__ == "__main__": unittest.main()
