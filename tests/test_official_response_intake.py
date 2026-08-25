from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import official_response_intake as intake  # noqa: E402
from official_blocker_policy import LIFECYCLE_BLOCKER,SORT_BLOCKER  # noqa: E402

STAMP="2026-08-26T00:00:00Z"
def response(blocker=LIFECYCLE_BLOCKER,answered=None,confirmations=(),denials=(),unanswered=(),ambiguity=(),source=intake.DIRECT_SUPPORT_CONFIRMATION,authority="DMM_AFFILIATE_SUPPORT",prior=None,reference="support-case-001"):
    return intake.SanitizedOfficialResponse("0.1","0.1",STAMP,source,authority,blocker,answered or {},tuple(unanswered),tuple(confirmations),tuple(denials),tuple(ambiguity),reference,prior or {})
def resolved(blocker=LIFECYCLE_BLOCKER):
    questions=intake.LIFECYCLE_QUESTION_IDS if blocker==LIFECYCLE_BLOCKER else intake.SORT_QUESTION_IDS
    return response(blocker,{q:intake.RESOLVED for q in questions},confirmations=questions)
def classify(value=None):return intake.classify_official_response(value or response())

class OfficialResponseIntakeTests(unittest.TestCase):
    def test_a_lifecycle_all_unanswered(self):self.assertEqual(classify().resolution_status,intake.UNRESOLVED)
    def test_b_lifecycle_partial(self):
        q=intake.LIFECYCLE_QUESTION_IDS[0];self.assertEqual(classify(response(answered={q:intake.RESOLVED},confirmations=(q,))).resolution_status,intake.PARTIALLY_RESOLVED)
    def test_c_lifecycle_all_resolved(self):self.assertEqual(classify(resolved()).resolution_status,intake.RESOLVED)
    def test_d_zero_only_resolved(self):
        q="CID_ZERO_RESULT_MEANING";self.assertFalse(classify(response(answered={q:intake.RESOLVED},confirmations=(q,))).gate_unlock_candidate)
    def test_e_affiliate_only_resolved(self):
        q="AFFILIATE_URL_ABSENCE_MEANING";self.assertFalse(classify(response(answered={q:intake.RESOLVED},confirmations=(q,))).gate_unlock_candidate)
    def test_f_requery_only_resolved(self):
        q="PERIODIC_REQUERY_RECOMMENDATION";self.assertFalse(classify(response(answered={q:intake.RESOLVED},confirmations=(q,))).gate_unlock_candidate)
    def test_g_page_handling_missing(self):
        q="NONVISIBLE_PAGE_HANDLING";v=resolved();a=dict(v.answered_questions);del a[q];self.assertFalse(classify(replace(v,answered_questions=a,explicit_confirmations=tuple(x for x in v.explicit_confirmations if x!=q))).gate_unlock_candidate)
    def test_h_contradictory_lifecycle(self):
        q=intake.LIFECYCLE_QUESTION_IDS[0];out=classify(response(answered={q:intake.CONTRADICTORY}));self.assertEqual(out.resolution_status,intake.CONTRADICTORY)
    def test_i_rank_only_resolved(self):
        qs=("RANK_SORT_DEFINITION","RANK_ORDERING_RULE");out=classify(response(SORT_BLOCKER,{q:intake.RESOLVED for q in qs},confirmations=qs));self.assertFalse(out.gate_unlock_candidate)
    def test_j_review_only_resolved(self):
        qs=("REVIEW_SORT_DEFINITION","REVIEW_ORDERING_RULE");out=classify(response(SORT_BLOCKER,{q:intake.RESOLVED for q in qs},confirmations=qs));self.assertFalse(out.gate_unlock_candidate)
    def test_k_definitions_without_position(self):
        qs=("RANK_SORT_DEFINITION","REVIEW_SORT_DEFINITION","RANK_ORDERING_RULE","REVIEW_ORDERING_RULE");self.assertFalse(classify(response(SORT_BLOCKER,{q:intake.RESOLVED for q in qs},confirmations=qs)).gate_unlock_candidate)
    def test_l_position_without_sort(self):
        qs=("OFFSET_MEANING","POSITION_MEANING","PUBLIC_POSITION_EXPRESSION");self.assertFalse(classify(response(SORT_BLOCKER,{q:intake.RESOLVED for q in qs},confirmations=qs)).gate_unlock_candidate)
    def test_m_full_semantics_candidate(self):self.assertTrue(classify(resolved(SORT_BLOCKER)).gate_unlock_candidate)
    def test_n_third_party_rejected(self):self.assertEqual(classify(response(source="THIRD_PARTY_BLOG")).resolution_status,intake.FAIL_CLOSED)
    def test_o_sdk_comment_rejected(self):self.assertEqual(classify(response(source="SDK_COMMENT")).resolution_status,intake.FAIL_CLOSED)
    def test_p_observed_behavior_rejected(self):self.assertEqual(classify(response(source="OBSERVED_API_BEHAVIOR")).resolution_status,intake.FAIL_CLOSED)
    def test_q_direct_support_allowed(self):self.assertNotEqual(classify().resolution_status,intake.FAIL_CLOSED)
    def test_r_official_docs_allowed(self):self.assertNotEqual(classify(response(source=intake.OFFICIAL_DOCUMENTATION,authority="DMM_OFFICIAL_DOCUMENTATION")).resolution_status,intake.FAIL_CLOSED)
    def test_s_explicit_confirmation_required(self):
        q=intake.LIFECYCLE_QUESTION_IDS[0];self.assertEqual(classify(response(answered={q:intake.RESOLVED})).resolution_status,intake.FAIL_CLOSED)
    def test_t_explicit_denial_can_resolve_question(self):
        q=intake.LIFECYCLE_QUESTION_IDS[0];self.assertEqual(classify(response(answered={q:intake.RESOLVED},denials=(q,))).resolution_status,intake.PARTIALLY_RESOLVED)
    def test_u_ambiguous_answer(self):
        q=intake.LIFECYCLE_QUESTION_IDS[0];out=classify(response(answered={q:intake.PARTIALLY_RESOLVED},ambiguity=(q,)));self.assertIn("AMBIGUOUS_RESPONSE",out.safe_reason_codes)
    def test_v_unanswered_retained(self):self.assertEqual(classify().next_required_questions,intake.LIFECYCLE_QUESTION_IDS)
    def test_w_contradiction_manual_review(self):
        q=intake.LIFECYCLE_QUESTION_IDS[0];self.assertTrue(classify(response(answered={q:intake.CONTRADICTORY})).manual_review_required)
    def test_x_newer_answer_no_silent_overwrite(self):
        q=intake.LIFECYCLE_QUESTION_IDS[0];out=classify(response(answered={q:intake.RESOLVED},confirmations=(q,),prior={q:intake.CONTRADICTORY}));self.assertEqual(out.resolution_status,intake.CONTRADICTORY)
    def test_y_rights_duplicate(self):self.assertEqual(classify(response(intake.RIGHTS_BLOCKER)).resolution_status,intake.DUPLICATE_CONFIRMATION)
    def test_z_rights_contradiction(self):
        out=classify(response(intake.RIGHTS_BLOCKER,answered={"RIGHTS":intake.CONTRADICTORY}));self.assertEqual(out.resolution_status,intake.CONTRADICTORY);self.assertTrue(out.manual_review_required)
    def test_aa_unknown_blocker(self):self.assertEqual(classify(response("UNKNOWN")).resolution_status,intake.FAIL_CLOSED)
    def test_ab_unknown_question(self):self.assertEqual(classify(response(answered={"UNKNOWN":intake.UNRESOLVED})).resolution_status,intake.FAIL_CLOSED)
    def test_ac_unknown_source(self):self.assertEqual(classify(response(source="FORUM")).resolution_status,intake.FAIL_CLOSED)
    def test_ad_unknown_version(self):self.assertEqual(classify(replace(response(),intake_version="9.9")).resolution_status,intake.FAIL_CLOSED)
    def test_ae_registry_version_mismatch(self):self.assertEqual(classify(replace(response(),registry_version="9.9")).resolution_status,intake.FAIL_CLOSED)
    def test_af_raw_email_key_rejected(self):self.assertEqual(classify({"raw_email_body":"body"}).resolution_status,intake.FAIL_CLOSED)
    def test_ag_email_address_leak(self):self.assertEqual(classify(replace(response(),safe_reference="person@example.com")).resolution_status,intake.FAIL_CLOSED)
    def test_ah_credential_leak(self):self.assertEqual(classify(replace(response(),safe_reference="api_id=fixture")).resolution_status,intake.FAIL_CLOSED)
    def test_ai_url_leak(self):self.assertEqual(classify(replace(response(),safe_reference="https://example.com/case")).resolution_status,intake.FAIL_CLOSED)
    def test_aj_absolute_path_leak(self):self.assertEqual(classify(replace(response(),safe_reference="C:\\Users\\case.txt")).resolution_status,intake.FAIL_CLOSED)
    def test_ak_raw_exception_mapping_rejected(self):self.assertEqual(classify({"exception":"fixture"}).resolution_status,intake.FAIL_CLOSED)
    def test_al_reason_deterministic(self):self.assertEqual(classify().safe_reason_codes,classify().safe_reason_codes)
    def test_am_next_questions_deterministic(self):self.assertEqual(classify().next_required_questions,classify().next_required_questions)
    def test_an_no_gate_mutation_api(self):self.assertFalse(any(name.startswith("set_") or name.startswith("update_") for name in dir(intake)))
    def test_ao_partial_unlock_false(self):
        q=intake.LIFECYCLE_QUESTION_IDS[0];self.assertFalse(classify(response(answered={q:intake.RESOLVED},confirmations=(q,))).gate_unlock_candidate)
    def test_ap_full_candidate_still_manual_review(self):self.assertTrue(classify(resolved()).manual_review_required)
    def test_aq_full_candidate_reason_boundary(self):self.assertIn("GATE_CHANGE_REQUIRES_SEPARATE_REVIEW",classify(resolved()).safe_reason_codes)
    def test_ar_confirmation_and_denial_contradict(self):
        q=intake.LIFECYCLE_QUESTION_IDS[0];out=classify(response(answered={q:intake.RESOLVED},confirmations=(q,),denials=(q,)));self.assertEqual(out.resolution_status,intake.CONTRADICTORY)
    def test_as_unknown_question_status(self):
        q=intake.LIFECYCLE_QUESTION_IDS[0];self.assertEqual(classify(response(answered={q:"UNKNOWN"})).resolution_status,intake.FAIL_CLOSED)
    def test_at_naive_received_at_rejected(self):self.assertEqual(classify(replace(response(),received_at="2026-08-26T00:00:00")).resolution_status,intake.FAIL_CLOSED)
    def test_au_safe_result_contract(self):
        self.assertEqual(set(classify().to_dict()),{"intake_version","affected_blocker","source_type","received_at","resolution_status","resolved_question_ids","unresolved_question_ids","contradictory_question_ids","gate_unlock_candidate","manual_review_required","safe_reason_codes","next_required_questions"})
    def test_av_safe_result_no_raw_payload(self):
        text=json.dumps(classify().to_dict()).lower();self.assertNotIn("raw_email",text);self.assertNotIn("sender",text);self.assertNotIn("credential",text);self.assertNotIn("traceback",text)
    def test_aw_intake_version(self):self.assertEqual(intake.INTAKE_VERSION,"0.1")
    def test_ax_internal_exception_safe(self):
        class Exploding(dict):
            def items(self):raise RuntimeError("fixture")
        self.assertEqual(classify(replace(response(),answered_questions=Exploding())).resolution_status,intake.FAIL_CLOSED)

if __name__=="__main__":unittest.main()
