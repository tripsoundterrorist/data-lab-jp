from __future__ import annotations

import copy, importlib.util, io, json, sys, unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import publication_gate as gate  # noqa: E402
import revenue_mvp_official_answer_matrix as matrix  # noqa: E402

PUBLIC_ID = "itm_0123456789abcdef01234567"
TIMESTAMP = "2026-08-23T06:00:00Z"
EXISTING_RIGHTS = ["title", "image_url", "item_url", "maker", "series", "actress", "genre"]

def json_bytes(value): return (json.dumps(value, separators=(",", ":")) + "\n").encode()
def artifact(publication_status="local_validation_only", rights=None, schema="0.1", policy="0.1"):
    item = {"public_id": PUBLIC_ID, "title": "Fixture title", "current_price": 1000, "last_observed_at": TIMESTAMP}
    manifest = {"public_schema_version": schema, "public_policy_version": policy, "publication_status": publication_status, "rights_review_required": EXISTING_RIGHTS if rights is None else rights, "generated_at": TIMESTAMP, "as_of": TIMESTAMP, "item_count": 1}
    index = {"public_schema_version": schema, "generated_at": TIMESTAMP, "as_of": TIMESTAMP, "items": [item]}
    detail = {"public_schema_version": schema, "generated_at": TIMESTAMP, "as_of": TIMESTAMP, "item": copy.deepcopy(item)}
    return {"manifest.json": json_bytes(manifest), "index.json": json_bytes(index), f"items/01/{PUBLIC_ID}.json": json_bytes(detail)}
def decoded(files): return {path: json.loads(value) for path, value in files.items()}
def encoded(documents): return {path: json_bytes(value) for path, value in documents.items()}

def allowed_answers():
    return {topic: matrix.AnswerDecision(matrix.ALLOWED) for topic in matrix.TOPIC_IDS}


class PublicationGateV03Tests(unittest.TestCase):
    def rights(self, field): return gate.evaluate_publication_gate(artifact(rights=[field]))
    def assert_forbidden(self, field):
        docs = decoded(artifact()); docs["index.json"]["items"][0][field] = "blocked"
        result = gate.evaluate_publication_gate(encoded(docs)); self.assertEqual(result.rights_gate, gate.CLOSED); self.assertIn("FORBIDDEN_FIELD_PRESENT", result.reason_codes)

    def test_a_approved_seven_existing_fields_pass_rights(self):
        result = gate.evaluate_publication_gate(artifact()); self.assertEqual(result.rights_gate, gate.PASS); self.assertEqual(result.approved_rights_fields, tuple(EXISTING_RIGHTS))
    def test_b_title_approved(self): self.assertEqual(self.rights("title").rights_gate, gate.PASS)
    def test_c_image_url_explicit_mapping(self): self.assertEqual(gate.PUBLIC_RIGHTS_FIELD_MAP["image_url"], "product_main_image")
    def test_d_item_url_explicit_mapping(self): self.assertEqual(gate.PUBLIC_RIGHTS_FIELD_MAP["item_url"], "product_page_url")
    def test_e_maker_approved(self): self.assertEqual(self.rights("maker").rights_gate, gate.PASS)
    def test_f_series_approved(self): self.assertEqual(self.rights("series").rights_gate, gate.PASS)
    def test_g_actress_approved(self): self.assertEqual(self.rights("actress").rights_gate, gate.PASS)
    def test_h_genre_approved(self): self.assertEqual(self.rights("genre").rights_gate, gate.PASS)
    def test_i_description_fails(self): self.assert_forbidden("product_description")
    def test_j_review_text_fails(self): self.assert_forbidden("user_review_text")
    def test_k_actress_face_image_fails(self): self.assert_forbidden("actress_api_face_image")
    def test_l_raw_api_fails(self): self.assert_forbidden("raw_api_response")
    def test_m_api_id_fails(self): self.assert_forbidden("api_id")
    def test_n_affiliate_id_fails(self): self.assert_forbidden("affiliate_id")
    def test_o_query_context_fails(self): self.assert_forbidden("query_context")
    def test_p_affiliate_url_fails(self): self.assert_forbidden("affiliate_url")
    def test_q_person_image_fails(self): self.assert_forbidden("person_list_image")
    def test_r_dmm_books_image_fails(self): self.assert_forbidden("dmm_books_product_image")
    def test_s_sample_video_fails(self): self.assert_forbidden("sample_video")
    def test_t_video_capture_fails(self): self.assert_forbidden("video_capture")
    def test_u_rights_pass_lifecycle_pending_overall_false(self):
        result = gate.evaluate_publication_gate(artifact()); self.assertEqual(result.lifecycle_gate, gate.PENDING_OFFICIAL_CONFIRMATION); self.assertFalse(result.overall_eligible)
    def test_v_rights_pass_local_status_overall_false(self):
        result = gate.evaluate_publication_gate(artifact()); self.assertEqual(result.publication_status, "local_validation_only"); self.assertFalse(result.overall_eligible)
    def test_w_rights_alone_cannot_publish(self): self.assertFalse(gate.evaluate_publication_gate(artifact("public")).overall_eligible)
    def test_x_lifecycle_not_inferred_from_rights(self): self.assertEqual(gate.evaluate_publication_gate(artifact()).lifecycle_gate, gate.PENDING_OFFICIAL_CONFIRMATION)
    def test_y_rank_semantics_remains_pending(self): self.assertIn("rank_sort_semantics", gate.evaluate_publication_gate(artifact()).pending_fields)
    def test_z_review_semantics_remains_pending(self): self.assertIn("review_sort_semantics", gate.evaluate_publication_gate(artifact()).pending_fields)
    def test_aa_unknown_rights_field_fails_closed(self):
        result = self.rights("implicit_alias"); self.assertEqual(result.rights_gate, gate.CLOSED); self.assertIn("UNKNOWN_RIGHTS_FIELD", result.reason_codes)
    def test_ab_rights_policy_version_mismatch(self):
        result = gate.evaluate_publication_gate(artifact(), rights_policy_version="9.9"); self.assertEqual(result.rights_gate, gate.CLOSED); self.assertIn("RIGHTS_POLICY_VERSION_MISMATCH", result.reason_codes)
    def test_ac_gate_version_fixed(self): self.assertEqual(gate.GATE_VERSION, "0.3")
    def test_ad_schema_version_mismatch(self): self.assertIn("UNSUPPORTED_SCHEMA_VERSION", gate.evaluate_publication_gate(artifact(schema="9.9")).reason_codes)
    def test_ae_public_policy_version_mismatch(self): self.assertIn("UNSUPPORTED_POLICY_VERSION", gate.evaluate_publication_gate(artifact(policy="9.9")).reason_codes)
    def test_af_current_expected_state(self):
        result = gate.evaluate_publication_gate(artifact()); self.assertEqual(result.rights_gate, gate.PASS); self.assertFalse(result.overall_eligible)
    def test_ag_reason_codes_deterministic(self):
        self.assertEqual(gate.evaluate_publication_gate(artifact()).reason_codes, gate.evaluate_publication_gate(artifact()).reason_codes)
    def test_ah_no_raw_evidence_text_leak(self): self.assertNotIn("DIRECT_SUPPORT_CONFIRMATION", json.dumps(gate.evaluate_publication_gate(artifact()).to_dict()))
    def test_ai_no_credential_or_path_leak(self):
        output = gate.evaluate_publication_gate(artifact()).to_dict(); self.assertFalse(any(key in output for key in ("credential", "file_path", "raw_response")))
    def test_aj_unknown_gate_status_fails_closed(self): self.assertFalse(gate.overall_from_gates(gate.PASS, "UNKNOWN"))
    def test_ak_all_known_passes_are_required(self): self.assertTrue(gate.overall_from_gates(gate.PASS, gate.PASS))
    def test_al_semantics_gate_is_pending(self): self.assertEqual(gate.evaluate_publication_gate(artifact()).semantics_gate, gate.PENDING_OFFICIAL_CONFIRMATION)
    def test_am_data_policy_passes_valid_fixture(self): self.assertEqual(gate.evaluate_publication_gate(artifact()).data_policy_gate, gate.PASS)
    def test_an_public_status_does_not_open_lifecycle(self): self.assertEqual(gate.evaluate_publication_gate(artifact("public")).lifecycle_gate, gate.PENDING_OFFICIAL_CONFIRMATION)
    def test_ao_result_contract(self):
        self.assertEqual(set(gate.evaluate_publication_gate(artifact()).to_dict()), {"gate_version", "overall_eligible", "publication_status", "rights_gate", "lifecycle_gate", "semantics_gate", "publication_status_gate", "data_policy_gate", "reason_codes", "approved_rights_fields", "blocked_fields", "pending_fields"})
    def test_ap_secret_pattern_fails(self):
        docs = decoded(artifact()); docs["index.json"]["items"][0]["title"] = "api_id=fixture-secret"; self.assertIn("SECRET_PATTERN_DETECTED", gate.evaluate_publication_gate(encoded(docs)).reason_codes)
    def test_aq_invalid_json_fails_closed(self):
        files = artifact(); files["manifest.json"] = b"bad"; self.assertFalse(gate.evaluate_publication_gate(files).overall_eligible)
    def test_ar_invalid_public_id_fails(self):
        docs = decoded(artifact()); docs["index.json"]["items"][0]["public_id"] = "bad"; self.assertIn("INVALID_PUBLIC_ID", gate.evaluate_publication_gate(encoded(docs)).reason_codes)
    def test_as_input_is_not_mutated(self):
        files = artifact(); before = copy.deepcopy(files); gate.evaluate_publication_gate(files); self.assertEqual(files, before)
    def test_at_compatibility_properties(self):
        result = gate.evaluate_publication_gate(artifact()); self.assertEqual(result.eligible, result.overall_eligible); self.assertEqual(result.reasons, result.reason_codes)

    def test_au_complete_answers_without_explicit_review_stay_pending(self):
        result = gate.evaluate_publication_gate(
            artifact("public"), official_answer_entries=allowed_answers()
        )
        self.assertEqual(result.lifecycle_gate, gate.PENDING_OFFICIAL_CONFIRMATION)
        self.assertEqual(result.semantics_gate, gate.PENDING_OFFICIAL_CONFIRMATION)
        self.assertFalse(result.overall_eligible)

    def test_av_explicitly_reviewed_complete_answers_unlock_official_gates(self):
        result = gate.evaluate_publication_gate(
            artifact("public"), official_answer_entries=allowed_answers(),
            explicit_official_answer_review_approval=True,
        )
        self.assertEqual(result.lifecycle_gate, gate.PASS)
        self.assertEqual(result.semantics_gate, gate.PASS)
        self.assertEqual(result.pending_fields, ())
        self.assertTrue(result.overall_eligible)

    def test_aw_unresolved_answers_cannot_be_approved_open(self):
        result = gate.evaluate_publication_gate(
            artifact("public"), official_answer_entries={},
            explicit_official_answer_review_approval=True,
        )
        self.assertFalse(result.overall_eligible)
        self.assertIn("OFFICIAL_ANSWER_REVIEW_REQUIRED", result.reason_codes)

    def test_ax_non_boolean_approval_fails_closed(self):
        result = gate.evaluate_publication_gate(
            artifact("public"), official_answer_entries=allowed_answers(),
            explicit_official_answer_review_approval=1,
        )
        self.assertFalse(result.overall_eligible)
        self.assertIn("OFFICIAL_ANSWER_APPROVAL_INVALID", result.reason_codes)

class BuilderBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("public_builder", SCRIPTS / "build-public-data.py")
        cls.builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.builder)
    def test_ay_production_mode_blocks_before_write(self):
        files = artifact()
        with mock.patch.object(self.builder, "build_documents", return_value=(files, {})), mock.patch.object(self.builder, "load_secret_values", return_value=[]), mock.patch.object(self.builder, "atomic_write") as writer, redirect_stdout(io.StringIO()): code = self.builder.main(["--publication-mode", "production", "--json"])
        self.assertEqual(code, 2); writer.assert_not_called()
    def test_az_local_validation_keeps_local_workflow(self):
        files = artifact()
        with mock.patch.object(self.builder, "build_documents", return_value=(files, {})), mock.patch.object(self.builder, "load_secret_values", return_value=[]), mock.patch.object(self.builder, "atomic_write") as writer, redirect_stdout(io.StringIO()): code = self.builder.main(["--publication-mode", "local-validation", "--json"])
        self.assertEqual(code, 0); writer.assert_called_once()

if __name__ == "__main__": unittest.main()
