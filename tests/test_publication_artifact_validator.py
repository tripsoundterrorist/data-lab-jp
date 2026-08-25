from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import publication_artifact_validator as validator  # noqa: E402

PUBLIC_ID = "itm_0123456789abcdef01234567"
STAMP = "2026-08-26T00:00:00Z"

def encoded(value): return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
def detail_digest(files):
    digest=hashlib.sha256()
    for path in sorted(key for key in files if key.startswith("items/")):
        digest.update(path.encode());digest.update(b"\0");digest.update(files[path])
    return digest.hexdigest()
def confidence(detailed=False):
    value={"score":80,"label":{"code":"HIGH","en":"High","ja":"高"},"version":"0.1"}
    if detailed:value.update({"components":{"freshness":80,"observation_depth":80,"metadata_completeness":80,"price_data":80,"temporal_confidence":80},"warnings":[]})
    return value
def price(detailed=False):
    value={"version":"0.1","observed_set_percentile":None,"percentile_method":"midrank","price_band":None}
    if detailed:value.update({"genre_comparisons":[],"maker_comparison":{"available":False,"comparisons":[]},"price_history":{"first_observed_price":1000,"first_price_observed_at":STAMP,"latest_observed_price":1000,"latest_price_observed_at":STAMP,"min_observed_price":1000,"max_observed_price":1000,"price_observation_count":1,"distinct_price_observation_dates":1,"price_observation_span_days":0},"warnings":[]})
    return value
def fixture():
    index_item={"public_id":PUBLIC_ID,"title":"Fixture","image_url":"https://pics.example/item.jpg","current_price":1000,"data_confidence":confidence(),"price_analysis":price(),"last_observed_at":STAMP}
    detail_item={"public_id":PUBLIC_ID,"title":"Fixture","image_url":"https://pics.example/item.jpg","item_url":"https://www.example/item","metadata":{"maker":[],"series":[],"actress":[],"genre":[]},"current_price":1000,"price_observed_at":STAMP,"last_observed_at":STAMP,"data_confidence":confidence(True),"price_analysis":price(True)}
    index={"public_schema_version":"0.1","generated_at":STAMP,"as_of":STAMP,"items":[index_item]}
    detail={"public_schema_version":"0.1","generated_at":STAMP,"as_of":STAMP,"item":detail_item}
    path=f"items/01/{PUBLIC_ID}.json";files={"index.json":encoded(index),path:encoded(detail)}
    manifest={"public_schema_version":"0.1","public_policy_version":"0.1","generated_at":STAMP,"as_of":STAMP,"item_count":1,"data_confidence_version":"0.1","price_analysis_version":"0.1","publication_status":"local_validation_only","rights_review_required":["title","image_url","item_url","maker","series","actress","genre"],"price_analysis_scope":"current_data_lab_observed_set","price_analysis_caveats":[],"index_path":"index.json","item_detail_pattern":"items/{shard}/{public_id}.json","index_sha256":hashlib.sha256(files["index.json"]).hexdigest(),"detail_aggregate_sha256":detail_digest(files)}
    files["manifest.json"]=encoded(manifest);return files
def docs(files):return {path:json.loads(content) for path,content in files.items()}
def files_from(documents):
    files={path:encoded(value) if not isinstance(value,bytes) else value for path,value in documents.items()}
    if "manifest.json" in files and "index.json" in files:
        manifest=json.loads(files["manifest.json"]);manifest["index_sha256"]=hashlib.sha256(files["index.json"]).hexdigest();manifest["detail_aggregate_sha256"]=detail_digest(files);files["manifest.json"]=encoded(manifest)
    return files
def result(files=None):return validator.validate_artifacts(fixture() if files is None else files)
def mutate(path, field, value):
    d=docs(fixture());target=d[path]
    for key in field[:-1]:target=target[key]
    target[field[-1]]=value;return files_from(d)

class ArtifactValidatorTests(unittest.TestCase):
    def assert_failed(self, files):self.assertEqual(result(files).artifact_validation,validator.FAIL_CLOSED)
    def test_a_valid_fixture_pass(self):self.assertEqual(result().artifact_validation,validator.PASS)
    def test_b_closed_gate_publication_false(self):self.assertFalse(result().publication_allowed)
    def test_c_malformed_manifest(self):f=fixture();f["manifest.json"]=b"{";self.assert_failed(f)
    def test_d_malformed_index(self):f=fixture();f["index.json"]=b"{";self.assert_failed(f)
    def test_e_malformed_detail(self):f=fixture();f[f"items/01/{PUBLIC_ID}.json"]=b"{";self.assert_failed(f)
    def test_f_missing_manifest(self):f=fixture();del f["manifest.json"];self.assertIn("MISSING_MANIFEST",result(f).reason_codes)
    def test_g_missing_index(self):f=fixture();del f["index.json"];self.assertIn("MISSING_INDEX",result(f).reason_codes)
    def test_h_missing_shard(self):f=fixture();del f[f"items/01/{PUBLIC_ID}.json"];self.assertIn("MISSING_DETAIL",result(f).reason_codes)
    def test_i_orphan_shard(self):f=fixture();f["items/ff/itm_ffffffffffffffffffffffff.json"]=f[f"items/01/{PUBLIC_ID}.json"];self.assertIn("ORPHAN_DETAIL",result(f).reason_codes)
    def test_j_duplicate_public_id(self):
        d=docs(fixture());d["index.json"]["items"].append(copy.deepcopy(d["index.json"]["items"][0]));d["manifest.json"]["item_count"]=2;self.assertIn("DUPLICATE_PUBLIC_ID",result(files_from(d)).reason_codes)
    def test_k_malformed_public_id(self):self.assertIn("INVALID_PUBLIC_ID",result(mutate("index.json",("items",0,"public_id"),"bad")).reason_codes)
    def test_l_wrong_public_id_prefix(self):self.assert_failed(mutate("index.json",("items",0,"public_id"),"cid_0123456789abcdef01234567"))
    def test_m_raw_content_id(self):self.assert_failed(mutate("index.json",("items",0,"content_id"),"raw"))
    def test_n_product_id(self):self.assert_failed(mutate("index.json",("items",0,"product_id"),"raw"))
    def test_o_affiliate_url(self):self.assert_failed(mutate("index.json",("items",0,"affiliate_url"),"https://x"))
    def test_p_api_id(self):self.assert_failed(mutate("index.json",("items",0,"api_id"),"x"))
    def test_q_affiliate_id(self):self.assert_failed(mutate("index.json",("items",0,"affiliate_id"),"x"))
    def test_r_query_context(self):self.assert_failed(mutate("index.json",("items",0,"query_context"),{}))
    def test_s_raw_api(self):self.assert_failed(mutate("index.json",("items",0,"raw_api_response"),{}))
    def test_t_description(self):self.assert_failed(mutate("index.json",("items",0,"product_description"),"x"))
    def test_u_review_text(self):self.assert_failed(mutate("index.json",("items",0,"user_review_text"),"x"))
    def test_v_actress_face(self):self.assert_failed(mutate("index.json",("items",0,"actress_api_face_image"),"x"))
    def test_w_source_position(self):self.assert_failed(mutate("index.json",("items",0,"source_position"),1))
    def test_x_source_offset(self):self.assert_failed(mutate("index.json",("items",0,"source_offset"),1))
    def test_y_collection_run(self):self.assert_failed(mutate("index.json",("items",0,"collection_run_id"),1))
    def test_z_unknown_field(self):self.assert_failed(mutate("index.json",("items",0,"unknown"),1))
    def test_aa_unknown_schema(self):self.assertIn("UNKNOWN_SCHEMA_VERSION",result(mutate("manifest.json",("public_schema_version",),"9.9")).reason_codes)
    def test_ab_unknown_policy(self):self.assertIn("UNKNOWN_POLICY_VERSION",result(mutate("manifest.json",("public_policy_version",),"9.9")).reason_codes)
    def test_ac_version_mismatch(self):self.assertIn("VERSION_MISMATCH",result(mutate("index.json",("public_schema_version",),"9.9")).reason_codes)
    def test_ad_javascript_url(self):self.assert_failed(mutate("index.json",("items",0,"image_url"),"javascript:alert(1)"))
    def test_ae_data_url(self):self.assert_failed(mutate("index.json",("items",0,"image_url"),"data:text/plain,x"))
    def test_af_file_url(self):self.assert_failed(mutate("index.json",("items",0,"image_url"),"file:///tmp/x"))
    def test_ag_localhost_url(self):self.assertIn("INVALID_URL",result(mutate("index.json",("items",0,"image_url"),"http://localhost/x")).reason_codes)
    def test_ah_windows_path(self):self.assertIn("PATH_LEAK",result(mutate("index.json",("items",0,"title"),"C:\\secret\\x")).reason_codes)
    def test_ai_unc_path(self):self.assertIn("PATH_LEAK",result(mutate("index.json",("items",0,"title"),"\\\\server\\share")).reason_codes)
    def test_aj_secret_like_value(self):self.assertIn("SECRET_LIKE_VALUE",result(mutate("index.json",("items",0,"title"),"api_id=fixture")).reason_codes)
    def test_ak_count_mismatch(self):self.assertIn("COUNT_MISMATCH",result(mutate("manifest.json",("item_count",),2)).reason_codes)
    def test_al_shard_duplicate(self):f=fixture();f[f"items/02/{PUBLIC_ID}.json"]=f[f"items/01/{PUBLIC_ID}.json"];self.assert_failed(f)
    def test_am_nested_forbidden(self):self.assert_failed(mutate(f"items/01/{PUBLIC_ID}.json",("item","metadata","maker"),[{"public_id":"mak_0123456789abcdef","name":"x","content_id":"x"}]))
    def test_an_valid_nullable_urls(self):
        d=docs(fixture());d["index.json"]["items"][0]["image_url"]=None;d[f"items/01/{PUBLIC_ID}.json"]["item"]["image_url"]=None;d[f"items/01/{PUBLIC_ID}.json"]["item"]["item_url"]=None;self.assertEqual(result(files_from(d)).artifact_validation,validator.PASS)
    def test_ao_empty_optional_metadata(self):self.assertEqual(result().artifact_validation,validator.PASS)
    def test_ap_public_status_contradiction(self):self.assertIn("CONTRADICTORY_PUBLICATION_STATE",result(mutate("manifest.json",("publication_status",),"public")).reason_codes)
    def test_aq_raw_exception_safe_failure(self):
        class Exploding(dict):
            def items(self):raise RuntimeError("fixture")
        out=result(Exploding());self.assertEqual(out.artifact_validation,validator.FAIL_CLOSED);self.assertEqual(out.reason_codes,("INTERNAL_ERROR",))
    def test_ar_deterministic_reasons(self):
        bad=mutate("index.json",("items",0,"content_id"),"raw");self.assertEqual(result(bad).reason_codes,result(bad).reason_codes)
    def test_as_derived_not_implemented_warning(self):
        out=result(mutate("index.json",("items",0,"derived_ranking"),1));self.assert_failed(mutate("index.json",("items",0,"derived_ranking"),1));self.assertIn("NOT_IMPLEMENTED_IN_SCHEMA",out.warnings)
    def test_at_index_digest_mismatch(self):
        f=fixture();m=json.loads(f["manifest.json"]);m["index_sha256"]="0"*64;f["manifest.json"]=encoded(m);self.assertIn("INDEX_DIGEST_MISMATCH",result(f).reason_codes)
    def test_au_detail_digest_mismatch(self):
        f=fixture();m=json.loads(f["manifest.json"]);m["detail_aggregate_sha256"]="0"*64;f["manifest.json"]=encoded(m);self.assertIn("DETAIL_DIGEST_MISMATCH",result(f).reason_codes)
    def test_av_safe_result_no_payload(self):
        text=json.dumps(result().to_dict());self.assertNotIn("Fixture",text);self.assertNotIn(PUBLIC_ID,text);self.assertNotIn("https://",text)
    def test_aw_validator_version(self):self.assertEqual(validator.VALIDATOR_VERSION,"0.1")

if __name__=="__main__":unittest.main()
