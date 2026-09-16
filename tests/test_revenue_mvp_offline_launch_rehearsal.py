from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from tests.test_revenue_mvp_offline_artifact_integration import (  # noqa: E402
    NOW, PUBLIC_ID, encoded, evidence, fixture, gate,
)
import revenue_mvp_offline_launch_rehearsal as rehearsal  # noqa: E402
import revenue_mvp_official_lifecycle_policy as policy  # noqa: E402
import revenue_mvp_offline_artifact_integration as integration  # noqa: E402
import revenue_mvp_offline_lifecycle_filter as filter_contract  # noqa: E402
import revenue_mvp_reduced_surface_semantics as surface  # noqa: E402
from product_verification import Observation, VerificationObservation  # noqa: E402


INDEX_FIELDS = ("public_id", "title", "last_observed_at")
DETAIL_FIELDS = (
    "public_id", "title", "last_observed_at", "affiliate_cta_eligible",
)
CTA = filter_contract.OfflineCtaEvidence(True, True, True, True)


def observation(value, affiliate):
    expected = (
        True if value is Observation.API_ITEM_VISIBLE
        else False if value is Observation.API_ITEM_NOT_RETURNED
        else None
    )
    return VerificationObservation(
        value, NOW, expected, affiliate, 200, ("PATH_SPECIFIC_FIXTURE",)
    )


def scenario(name, observed, *, fresh=True):
    decision = policy.evaluate_official_lifecycle_policy(observed)
    filtered = filter_contract.filter_offline_artifact_candidate(
        decision, gate(), freshness_confirmed=fresh,
        api_order_preserved=True, index_field_names=INDEX_FIELDS,
        detail_field_names=DETAIL_FIELDS, cta_evidence=CTA,
    )
    reviewed = surface.review_reduced_surface(
        contract_version=surface.CONTRACT_VERSION,
        lifecycle_decision=decision, source_sort="rank",
        public_order_matches_api=True, api_observed_at=NOW,
        requested_sort_label=surface.SORT_LABELS["rank"],
        timestamp_label=surface.TIMESTAMP_LABEL,
        public_semantic_fields=surface.ALLOWED_PUBLIC_SEMANTIC_FIELDS,
        public_claim_codes=surface.ALLOWED_CLAIMS,
        affiliate_url_validated=True, cta_requested=True,
        disclosure_visible=True, disclosure_proximate=True,
    )
    item_evidence = integration.OfflineArtifactItemEvidence(filtered, reviewed)
    return rehearsal.ExclusionScenario(name, observed, {PUBLIC_ID: item_evidence})


def excluded_scenarios():
    return (
        scenario("NON_TARGET", observation(Observation.API_ITEM_NOT_RETURNED, None)),
        scenario("AFFILIATE_URL_MISSING", observation(Observation.API_ITEM_VISIBLE, False)),
        scenario("AFFILIATE_URL_UNKNOWN", observation(Observation.API_ITEM_VISIBLE, None)),
        scenario("API_ERROR", observation(Observation.API_ERROR, None)),
        scenario("RATE_LIMITED", observation(Observation.API_RATE_LIMITED, None)),
        scenario("STALE", observation(Observation.API_ITEM_VISIBLE, True), fresh=False),
    )


def forbidden_scenarios():
    scenarios = []
    for field in ("first_position", "source_position", "offset", "rank", "top", "latest"):
        files = fixture()
        documents = {path: json.loads(content) for path, content in files.items()}
        documents["index.json"]["items"][0][field] = 1
        files["index.json"] = encoded(documents["index.json"])
        scenarios.append(rehearsal.ForbiddenScenario(field, files))
    return tuple(scenarios)


class OfflineLaunchRehearsalTests(unittest.TestCase):
    def test_complete_offline_rehearsal(self):
        result = rehearsal.run_offline_launch_rehearsal(
            fixture(), {PUBLIC_ID: evidence()}, excluded_scenarios(),
            forbidden_scenarios(),
        )
        self.assertEqual(result.status, rehearsal.REHEARSAL_COMPLETE)
        self.assertTrue(result.candidate_index_detail_consistent)
        self.assertTrue(result.candidate_cta_disabled)
        self.assertEqual(result.exclusions_verified, result.exclusions_required)
        self.assertTrue(result.manifest_count_digest_verified)
        self.assertTrue(result.forbidden_inputs_fail_closed)
        self.assertTrue(result.rollback_deterministic)
        self.assertIsNotNone(result.rollback_source_sha256)
        self.assertFalse(result.production_publication_allowed)
        self.assertFalse(result.publication_gate_change_allowed)
        self.assertFalse(result.external_io_performed)

    def test_rollback_is_byte_exact_and_does_not_alias_source(self):
        source = fixture()
        restored = rehearsal.restore_local_validation_snapshot(source)
        self.assertEqual(restored, source)
        self.assertIsNot(restored, source)
        restored["index.json"] = b"changed"
        self.assertNotEqual(restored, source)

    def test_invalid_or_nonlocal_snapshot_cannot_be_restored(self):
        files = fixture()
        manifest = json.loads(files["manifest.json"])
        manifest["publication_status"] = "public"
        files["manifest.json"] = encoded(manifest)
        self.assertEqual(rehearsal.restore_local_validation_snapshot(files), {})
        self.assertEqual(rehearsal.restore_local_validation_snapshot(None), {})

    def test_missing_exclusion_or_forbidden_scenario_fails_closed(self):
        cases = (
            (excluded_scenarios()[:-1], forbidden_scenarios()),
            (excluded_scenarios(), ()),
        )
        for exclusions, forbidden in cases:
            with self.subTest(exclusions=len(exclusions), forbidden=len(forbidden)):
                result = rehearsal.run_offline_launch_rehearsal(
                    fixture(), {PUBLIC_ID: evidence()}, exclusions, forbidden
                )
                self.assertEqual(result.status, rehearsal.FAIL_CLOSED)
                self.assertFalse(result.production_publication_allowed)

    def test_swapped_or_reused_exclusion_evidence_fails_closed(self):
        scenarios = list(excluded_scenarios())
        scenarios[0] = replace(
            scenarios[0], observation=scenarios[3].observation
        )
        result = rehearsal.run_offline_launch_rehearsal(
            fixture(), {PUBLIC_ID: evidence()}, tuple(scenarios),
            forbidden_scenarios(),
        )
        self.assertEqual(result.status, rehearsal.FAIL_CLOSED)
        self.assertIn("EXCLUSION_SCENARIO_MISMATCH", result.reason_codes)

        scenarios = list(excluded_scenarios())
        scenarios[3] = replace(
            scenarios[3],
            evidence_by_public_id=scenarios[0].evidence_by_public_id,
        )
        result = rehearsal.run_offline_launch_rehearsal(
            fixture(), {PUBLIC_ID: evidence()}, tuple(scenarios),
            forbidden_scenarios(),
        )
        self.assertEqual(result.status, rehearsal.FAIL_CLOSED)
        self.assertIn("EXCLUSION_FILTER_EVIDENCE_MISMATCH", result.reason_codes)

    def test_tampered_candidate_evidence_fails_closed(self):
        item = evidence()
        unsafe = replace(
            item.lifecycle, publication_allowed=True,
        )
        result = rehearsal.run_offline_launch_rehearsal(
            fixture(), {PUBLIC_ID: replace(item, lifecycle=unsafe)},
            excluded_scenarios(), forbidden_scenarios(),
        )
        self.assertEqual(result.status, rehearsal.FAIL_CLOSED)

    def test_source_has_no_external_or_filesystem_io(self):
        source = Path(rehearsal.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "open(", "read_text(", "write_text(", "sqlite3", "requests",
            "urllib", "subprocess", "fetch(", "scheduler", "deploy",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
