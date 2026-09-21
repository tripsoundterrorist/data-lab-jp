from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import publication_gate  # noqa: E402
import revenue_mvp_official_lifecycle_policy as lifecycle  # noqa: E402
import revenue_mvp_offline_lifecycle_filter as adapter  # noqa: E402
import revenue_mvp_offline_review_candidate_eligibility as review_adapter  # noqa: E402
from product_verification import Observation, VerificationObservation  # noqa: E402


NOW = datetime(2026, 9, 16, 6, 0, tzinfo=timezone.utc)
INDEX_FIELDS = ("public_id", "title", "last_observed_at")
DETAIL_FIELDS = (
    "public_id", "title", "last_observed_at", "affiliate_cta_eligible",
)
CTA = adapter.OfflineCtaEvidence(True, True, True, True)


def observation(value: Observation, affiliate: bool | None):
    expected = (
        True if value is Observation.API_ITEM_VISIBLE
        else False if value is Observation.API_ITEM_NOT_RETURNED
        else None
    )
    return VerificationObservation(
        value, NOW, expected, affiliate, 200, ("SANITIZED_FIXTURE",)
    )


def decision(
    value: Observation = Observation.API_ITEM_VISIBLE,
    affiliate: bool | None = True,
    inventory: lifecycle.InventorySignal = lifecycle.InventorySignal.UNKNOWN,
):
    return lifecycle.evaluate_official_lifecycle_policy(
        observation(value, affiliate), inventory_signal=inventory
    )


def gate(eligible: bool):
    status = publication_gate.PASS if eligible else publication_gate.CLOSED
    return publication_gate.PublicationGateResult(
        publication_gate.GATE_VERSION,
        eligible,
        "public" if eligible else publication_gate.LOCAL_VALIDATION_ONLY,
        status,
        status,
        status,
        status,
        status,
        (),
        (),
        (),
        (),
    )


def apply(value, gate_value, *, fresh=True, order=True, cta=CTA, **changes):
    arguments = {
        "freshness_confirmed": fresh,
        "api_order_preserved": order,
        "index_field_names": INDEX_FIELDS,
        "detail_field_names": DETAIL_FIELDS,
        "cta_evidence": cta,
    }
    arguments.update(changes)
    return adapter.filter_offline_artifact_candidate(
        value, gate_value, **arguments
    )


def review(value, gate_value, *, fresh=True, order=False, **changes):
    _ = order, changes
    return review_adapter.evaluate(value, gate_value, freshness_confirmed=fresh)


class OfflineLifecycleFilterTests(unittest.TestCase):
    def assert_not_public(self, result):
        self.assertFalse(result.production_cta_allowed)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.latestness_claim_allowed)
        self.assertFalse(result.public_rank_allowed)
        self.assertFalse(result.source_position_allowed)
        self.assertFalse(result.update_frequency_claim_allowed)

    def test_candidate_alone_cannot_pass_closed_publication_gate(self):
        result = apply(decision(), gate(False))
        self.assertEqual(result.status, adapter.EXCLUDED)
        self.assertFalse(result.include_in_offline_artifact)
        self.assertFalse(result.affiliate_cta_candidate)
        self.assertIn("CANDIDATE_ALONE_INSUFFICIENT", result.reason_codes)
        self.assert_not_public(result)

    def test_closed_gate_can_identify_review_only_candidate_without_artifact_or_cta(self):
        actual = apply(decision(), gate(False))
        candidate = review(decision(), gate(False))
        self.assertEqual(actual.status, adapter.EXCLUDED)
        self.assertEqual(candidate.status, review_adapter.REVIEW_CANDIDATE)
        self.assertTrue(candidate.eligible)
        self.assertFalse(candidate.cta_allowed)
        self.assertFalse(candidate.api_order_label_allowed)
        self.assertFalse(candidate.publication_allowed)
        self.assertFalse(candidate.affiliate_eligibility_allowed)
        self.assertFalse(candidate.gate_mutation_allowed)

    def test_unavailable_missing_link_error_and_rate_limit_are_excluded(self):
        cases = (
            decision(Observation.API_ITEM_NOT_RETURNED, None),
            decision(Observation.API_ITEM_VISIBLE, False),
            decision(Observation.API_ITEM_VISIBLE, None),
            decision(Observation.API_ERROR, None),
            decision(Observation.API_RATE_LIMITED, None),
        )
        for value in cases:
            with self.subTest(state=value.state):
                result = apply(value, gate(True))
                self.assertEqual(result.status, adapter.EXCLUDED)
                self.assertFalse(result.include_in_offline_artifact)
                self.assertFalse(result.affiliate_cta_candidate)
                self.assert_not_public(result)

    def test_preorder_or_out_of_stock_alone_does_not_exclude(self):
        for signal in (
            lifecycle.InventorySignal.PREORDER,
            lifecycle.InventorySignal.OUT_OF_STOCK,
        ):
            with self.subTest(signal=signal):
                result = apply(decision(inventory=signal), gate(True))
                self.assertEqual(result.status, adapter.INCLUDE_CANDIDATE)
                self.assertTrue(result.include_in_offline_artifact)
                self.assertTrue(result.affiliate_cta_candidate)
                self.assertTrue(result.observation_timestamp_allowed)
                self.assertEqual(result.observation_observed_at, NOW.isoformat())
                self.assert_not_public(result)

    def test_stale_candidate_is_removed_without_latestness_claim(self):
        result = apply(decision(), gate(True), fresh=False)
        self.assertEqual(result.status, adapter.EXCLUDED)
        self.assertFalse(result.include_in_offline_artifact)
        self.assertFalse(result.observation_timestamp_allowed)
        self.assert_not_public(result)

    def test_unknown_contradictory_or_permissive_input_fails_closed(self):
        cases = (
            (None, gate(True), {}),
            (decision(), None, {}),
            (decision(), gate(True), {"fresh": 1}),
            (
                replace(decision(), publication_gate_change_allowed=True),
                gate(True),
                {},
            ),
        )
        for lifecycle_value, gate_value, changes in cases:
            with self.subTest(value=lifecycle_value):
                result = apply(lifecycle_value, gate_value, **changes)
                self.assertEqual(result.status, adapter.FAIL_CLOSED)
                self.assertFalse(result.include_in_offline_artifact)
                self.assert_not_public(result)

    def test_cta_requires_same_item_observation_url_validation_pr_and_gate(self):
        for field in (
            "same_item", "same_observation", "affiliate_url_validated",
            "pr_disclosure_present",
        ):
            with self.subTest(field=field):
                evidence = replace(CTA, **{field: False})
                result = apply(decision(), gate(True), cta=evidence)
                self.assertTrue(result.include_in_offline_artifact)
                self.assertFalse(result.affiliate_cta_candidate)
                self.assertIn("CTA_EVIDENCE_INCOMPLETE", result.reason_codes)

    def test_index_and_detail_explicitly_reject_position_rank_and_top_fields(self):
        for field in adapter.PROHIBITED_ARTIFACT_FIELDS:
            with self.subTest(field=field):
                result = apply(
                    decision(), gate(True),
                    index_field_names=INDEX_FIELDS + (field,),
                )
                self.assertEqual(result.status, adapter.FAIL_CLOSED)
                self.assertFalse(result.include_in_offline_artifact)

    def test_changed_api_order_suppresses_api_order_label(self):
        result = apply(decision(), gate(True), order=False)
        self.assertTrue(result.include_in_offline_artifact)
        self.assertFalse(result.api_order_label_allowed)
        self.assertIn("API_ORDER_LABEL_SUPPRESSED", result.reason_codes)

    def test_adapter_has_no_artifact_io_or_runtime_connection(self):
        source = Path(adapter.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "open(", "read_text(", "write_text(", "sqlite3", "requests",
            "urllib", "subprocess", "fetch(", "build_public", "scheduler",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
