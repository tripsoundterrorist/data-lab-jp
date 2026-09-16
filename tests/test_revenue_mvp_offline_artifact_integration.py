from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import publication_gate  # noqa: E402
import revenue_mvp_official_lifecycle_policy as policy  # noqa: E402
import revenue_mvp_offline_artifact_integration as integration  # noqa: E402
import revenue_mvp_offline_lifecycle_filter as filter_contract  # noqa: E402
import revenue_mvp_reduced_surface_semantics as surface  # noqa: E402
from product_verification import Observation, VerificationObservation  # noqa: E402


NOW = datetime(2026, 9, 16, 6, 0, tzinfo=timezone.utc)
PUBLIC_ID = "itm_0123456789abcdef01234567"


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def confidence(detailed=False):
    value = {"score": 80, "label": {"code": "HIGH", "en": "High", "ja": "高"}, "version": "0.1"}
    if detailed:
        value.update({"components": {"freshness": 80, "observation_depth": 80, "metadata_completeness": 80, "price_data": 80, "temporal_confidence": 80}, "warnings": []})
    return value


def price(detailed=False):
    value = {"version": "0.1", "observed_set_percentile": None, "percentile_method": "midrank", "price_band": None}
    if detailed:
        value.update({"genre_comparisons": [], "maker_comparison": {"available": False, "comparisons": []}, "price_history": {"first_observed_price": 1000, "first_price_observed_at": NOW.isoformat(), "latest_observed_price": 1000, "latest_price_observed_at": NOW.isoformat(), "min_observed_price": 1000, "max_observed_price": 1000, "price_observation_count": 1, "distinct_price_observation_dates": 1, "price_observation_span_days": 0}, "warnings": []})
    return value


def fixture():
    item = {
        "public_id": PUBLIC_ID, "title": "Fixture", "image_url": None,
        "current_price": 1000, "data_confidence": confidence(),
        "price_analysis": price(),
        "last_observed_at": NOW.isoformat(),
    }
    detail_item = dict(item)
    detail_item.update({"item_url": None, "affiliate_cta_eligible": False, "metadata": {"maker": [], "series": [], "actress": [], "genre": []}, "price_observed_at": NOW.isoformat(), "data_confidence": confidence(True), "price_analysis": price(True)})
    detail_path = f"items/01/{PUBLIC_ID}.json"
    files = {
        "index.json": encoded({"public_schema_version": "0.1", "generated_at": NOW.isoformat(), "as_of": NOW.isoformat(), "items": [item]}),
        detail_path: encoded({"public_schema_version": "0.1", "generated_at": NOW.isoformat(), "as_of": NOW.isoformat(), "item": detail_item}),
    }
    digest = hashlib.sha256(); digest.update(detail_path.encode()); digest.update(b"\0"); digest.update(files[detail_path])
    manifest = {"public_schema_version": "0.1", "public_policy_version": "0.1", "generated_at": NOW.isoformat(), "as_of": NOW.isoformat(), "item_count": 1, "data_confidence_version": "0.1", "price_analysis_version": "0.1", "publication_status": "local_validation_only", "rights_review_required": ["title", "image_url", "item_url", "maker", "series", "actress", "genre"], "price_analysis_scope": "current_data_lab_observed_set", "price_analysis_caveats": [], "index_path": "index.json", "item_detail_pattern": "items/{shard}/{public_id}.json", "index_sha256": hashlib.sha256(files["index.json"]).hexdigest(), "detail_aggregate_sha256": digest.hexdigest()}
    files["manifest.json"] = encoded(manifest)
    return files


def gate():
    return publication_gate.PublicationGateResult(publication_gate.GATE_VERSION, True, "public", *(publication_gate.PASS,) * 5, (), (), (), ())


def evidence(include=True):
    observation = VerificationObservation(Observation.API_ITEM_VISIBLE, NOW, True, True, 200, ("FIXTURE",))
    lifecycle = policy.evaluate_official_lifecycle_policy(observation)
    filtered = filter_contract.filter_offline_artifact_candidate(
        lifecycle, gate(), freshness_confirmed=True, api_order_preserved=True,
        index_field_names=("public_id", "title", "last_observed_at"),
        detail_field_names=("public_id", "title", "last_observed_at", "affiliate_cta_eligible"),
        cta_evidence=filter_contract.OfflineCtaEvidence(True, True, True, True),
    )
    reviewed = surface.review_reduced_surface(
        contract_version=surface.CONTRACT_VERSION, lifecycle_decision=lifecycle,
        source_sort="rank", public_order_matches_api=True,
        api_observed_at=NOW, requested_sort_label=surface.SORT_LABELS["rank"],
        timestamp_label=surface.TIMESTAMP_LABEL,
        public_semantic_fields=surface.ALLOWED_PUBLIC_SEMANTIC_FIELDS,
        public_claim_codes=surface.ALLOWED_CLAIMS, affiliate_url_validated=True,
        cta_requested=True, disclosure_visible=True, disclosure_proximate=True,
    )
    if not include:
        filtered = replace(filtered, status=filter_contract.EXCLUDED, include_in_offline_artifact=False, affiliate_cta_candidate=False)
    return integration.OfflineArtifactItemEvidence(filtered, reviewed)


class OfflineArtifactIntegrationTests(unittest.TestCase):
    def test_included_item_updates_both_index_and_detail_atomically(self):
        result = integration.filter_offline_publication_artifacts(fixture(), {PUBLIC_ID: evidence()})
        self.assertEqual(result.status, integration.COMPLETE)
        self.assertEqual((result.included_item_count, result.excluded_item_count), (1, 0))
        documents = {path: json.loads(value) for path, value in result.files.items()}
        self.assertEqual(len(documents["index.json"]["items"]), 1)
        self.assertFalse(documents[f"items/01/{PUBLIC_ID}.json"]["item"]["affiliate_cta_eligible"])
        self.assertFalse(result.production_publication_allowed)

    def test_exclusion_removes_index_and_detail_and_rebuilds_digests(self):
        result = integration.filter_offline_publication_artifacts(fixture(), {PUBLIC_ID: evidence(False)})
        self.assertEqual(result.status, integration.COMPLETE)
        self.assertEqual((result.included_item_count, result.excluded_item_count), (0, 1))
        self.assertNotIn(f"items/01/{PUBLIC_ID}.json", result.files)
        index = json.loads(result.files["index.json"])
        manifest = json.loads(result.files["manifest.json"])
        self.assertEqual(index["items"], [])
        self.assertEqual(manifest["item_count"], 0)
        self.assertEqual(manifest["detail_aggregate_sha256"], hashlib.sha256().hexdigest())

    def test_timestamp_provenance_mismatch_fails_to_include(self):
        item_evidence = evidence()
        mismatch = replace(item_evidence.reduced_surface, api_observed_at="2026-09-16T07:00:00+00:00")
        result = integration.filter_offline_publication_artifacts(fixture(), {PUBLIC_ID: replace(item_evidence, reduced_surface=mismatch)})
        self.assertEqual(result.included_item_count, 0)

    def test_missing_extra_or_wrong_evidence_fails_closed(self):
        for value in ({}, {PUBLIC_ID: None}, {PUBLIC_ID: evidence(), "itm_ffffffffffffffffffffffff": evidence()}):
            with self.subTest(value=value):
                result = integration.filter_offline_publication_artifacts(fixture(), value)
                self.assertEqual(result.status, integration.FAIL_CLOSED)
                self.assertEqual(result.files, {})

    def test_prohibited_public_fields_fail_before_filter(self):
        for field in ("first_position", "source_position", "offset", "rank", "top"):
            with self.subTest(field=field):
                files = fixture(); documents = {path: json.loads(value) for path, value in files.items()}
                documents["index.json"]["items"][0][field] = 1
                files["index.json"] = encoded(documents["index.json"])
                result = integration.filter_offline_publication_artifacts(files, {PUBLIC_ID: evidence()})
                self.assertEqual(result.status, integration.FAIL_CLOSED)

    def test_source_has_no_io_or_runtime_connection(self):
        source = Path(integration.__file__).read_text(encoding="utf-8")
        for forbidden in ("open(", "read_text(", "write_text(", "sqlite3", "requests", "urllib", "subprocess", "fetch(", "scheduler"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
