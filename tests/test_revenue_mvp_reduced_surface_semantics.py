from dataclasses import replace
from datetime import datetime, timezone
import inspect
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import revenue_mvp_official_lifecycle_policy as lifecycle  # noqa: E402
import revenue_mvp_reduced_surface_semantics as surface  # noqa: E402
from product_verification import Observation, VerificationObservation  # noqa: E402


NOW = datetime(2026, 9, 16, 7, 0, tzinfo=timezone.utc)


def lifecycle_candidate() -> lifecycle.OfficialLifecycleDecision:
    observation = VerificationObservation(
        observation=Observation.API_ITEM_VISIBLE,
        observed_at=NOW,
        expected_content_id_match=True,
        affiliate_link_observed=True,
        source_status_code=200,
        reason_codes=("SANITIZED_FIXTURE",),
    )
    return lifecycle.evaluate_official_lifecycle_policy(observation)


def valid_input(**changes):
    value = {
        "contract_version": surface.CONTRACT_VERSION,
        "lifecycle_decision": lifecycle_candidate(),
        "source_sort": "rank",
        "public_order_matches_api": True,
        "api_observed_at": NOW,
        "requested_sort_label": surface.SORT_LABELS["rank"],
        "timestamp_label": surface.TIMESTAMP_LABEL,
        "public_semantic_fields": tuple(sorted(surface.ALLOWED_PUBLIC_SEMANTIC_FIELDS)),
        "public_claim_codes": tuple(sorted(surface.ALLOWED_CLAIMS)),
        "affiliate_url_validated": True,
        "cta_requested": True,
        "disclosure_visible": True,
        "disclosure_proximate": True,
    }
    value.update(changes)
    return value


class ReducedSurfaceSemanticsTests(unittest.TestCase):
    def assert_no_activation(self, result):
        self.assertFalse(result.publication_gate_change_allowed)
        self.assertFalse(result.production_publication_allowed)
        self.assertFalse(result.external_send_allowed)

    def test_rank_and_review_are_review_candidates_with_fixed_labels(self):
        for source_sort in ("rank", "review"):
            with self.subTest(source_sort=source_sort):
                result = surface.review_reduced_surface(
                    **valid_input(
                        source_sort=source_sort,
                        requested_sort_label=surface.SORT_LABELS[source_sort],
                    )
                )
                self.assertEqual(result.status, surface.REVIEW_CANDIDATE)
                self.assertTrue(result.surface_contract_satisfied)
                self.assertTrue(result.gate_review_candidate)
                self.assertEqual(result.allowed_sort_label, surface.SORT_LABELS[source_sort])
                self.assertEqual(result.timestamp_label, "API取得日時")
                self.assertEqual(result.api_observed_at, NOW.isoformat())
                self.assertTrue(result.cta_candidate)
                self.assert_no_activation(result)

    def test_review_candidate_still_cannot_unlock_or_publish(self):
        result = surface.review_reduced_surface(**valid_input())
        self.assertIn("SEPARATE_GATE_REVIEW_REQUIRED", result.reason_codes)
        self.assertIn("PUBLICATION_REMAINS_FORBIDDEN", result.reason_codes)
        self.assert_no_activation(result)

    def test_non_candidate_lifecycle_is_blocked(self):
        excluded = replace(
            lifecycle_candidate(),
            state=lifecycle.EligibilityState.EXCLUDED,
            public_listing_candidate=False,
            affiliate_candidate=False,
            exclude_from_public_site=True,
        )
        result = surface.review_reduced_surface(
            **valid_input(lifecycle_decision=excluded)
        )
        self.assertEqual(result.status, surface.BLOCKED)
        self.assertIn("LIFECYCLE_CANDIDATE_REQUIRED", result.reason_codes)
        self.assert_no_activation(result)

    def test_every_forbidden_field_is_blocked(self):
        for field in surface.FORBIDDEN_PUBLIC_FIELDS:
            with self.subTest(field=field):
                result = surface.review_reduced_surface(
                    **valid_input(
                        public_semantic_fields=tuple(
                            sorted(surface.ALLOWED_PUBLIC_SEMANTIC_FIELDS | {field})
                        )
                    )
                )
                self.assertEqual(result.status, surface.BLOCKED)
                self.assertIn("FORBIDDEN_PUBLIC_FIELD", result.reason_codes)

    def test_every_forbidden_claim_is_blocked(self):
        for claim in surface.FORBIDDEN_CLAIMS:
            with self.subTest(claim=claim):
                result = surface.review_reduced_surface(
                    **valid_input(
                        public_claim_codes=tuple(sorted(surface.ALLOWED_CLAIMS | {claim}))
                    )
                )
                self.assertEqual(result.status, surface.BLOCKED)
                self.assertIn("FORBIDDEN_PUBLIC_CLAIM", result.reason_codes)

    def test_order_timestamp_and_fixed_labels_fail_closed(self):
        cases = (
            {"public_order_matches_api": False},
            {"api_observed_at": datetime(2026, 9, 16, 7, 0)},
            {"requested_sort_label": "公式ランキング"},
            {"timestamp_label": "最終更新日時"},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                result = surface.review_reduced_surface(**valid_input(**changes))
                self.assertNotEqual(result.status, surface.REVIEW_CANDIDATE)
                self.assert_no_activation(result)

    def test_cta_requires_validated_url_and_proximate_disclosure(self):
        cases = (
            {"affiliate_url_validated": False},
            {"cta_requested": False},
            {"disclosure_visible": False},
            {"disclosure_proximate": False},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                result = surface.review_reduced_surface(**valid_input(**changes))
                self.assertEqual(result.status, surface.BLOCKED)
                self.assertFalse(result.cta_candidate)
                self.assert_no_activation(result)

    def test_input_contract_accepts_no_url_rank_offset_or_update_value(self):
        names = set(surface.accepted_input_names())
        self.assertNotIn("affiliate_url", names)
        self.assertNotIn("rank_number", names)
        self.assertNotIn("offset", names)
        self.assertNotIn("first_position", names)
        self.assertNotIn("source_position", names)
        self.assertNotIn("update_frequency", names)
        source = inspect.getsource(surface)
        self.assertNotIn("requests", source)
        self.assertNotIn("urllib", source)
        self.assertNotIn("sqlite3", source)

    def test_malformed_inputs_fail_closed(self):
        cases = (
            {"contract_version": "999"},
            {"source_sort": "date"},
            {"affiliate_url_validated": 1},
            {"public_semantic_fields": "api_observed_at"},
            {"public_claim_codes": None},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                result = surface.review_reduced_surface(**valid_input(**changes))
                self.assertEqual(result.status, surface.INVALID_INPUT)
                self.assert_no_activation(result)


if __name__ == "__main__":
    unittest.main()
