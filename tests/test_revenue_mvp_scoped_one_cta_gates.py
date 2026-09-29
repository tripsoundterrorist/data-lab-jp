from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_scoped_one_cta_gates as subject  # noqa: E402

NOW = datetime(2026, 9, 29, 3, 0, tzinfo=timezone.utc)
SHA = {
    "official": "1" * 64, "artifact": "2" * 64,
    "candidate": "3" * 64, "source": "4" * 64,
    "compliance": "5" * 64, "user": "6" * 64,
    "pages": "7" * 64,
}
PUBLIC_ID = "itm_" + "a" * 24


def evidence(**changes):
    value = {
        "official_response_sha256": SHA["official"],
        "official_response_status": subject.OFFICIAL_STATUS,
        "artifact_sha256": SHA["artifact"],
        "candidate_sha256": SHA["candidate"],
        "source_sha256": SHA["source"],
        "surface": "/items/", "route_prefix": "/go/", "public_id": PUBLIC_ID,
        "cta_count": 1, "item_count": 100,
        "observed_at": "2026-09-29T02:30:00Z",
        "valid_until": "2026-09-30T02:30:00Z",
        "compliance_approval_sha256": SHA["compliance"],
        "compliance_candidate_sha256": SHA["candidate"],
        "user_approval_sha256": SHA["user"],
        "user_candidate_sha256": SHA["candidate"],
        "free_confirmed_at": "2026-09-29T02:45:00Z",
        "rollback_pages_sha256": SHA["pages"],
        "rollback_worker_version": "worker-version-exact",
    }
    value.update(changes)
    return value


def anchors(**changes):
    value = {
        "official_response_sha256": SHA["official"],
        "artifact_sha256": SHA["artifact"],
        "candidate_sha256": SHA["candidate"],
        "source_sha256": SHA["source"], "public_id": PUBLIC_ID,
        "compliance_approval_sha256": SHA["compliance"],
        "user_approval_sha256": SHA["user"],
        "rollback_pages_sha256": SHA["pages"],
        "rollback_worker_version": "worker-version-exact",
        "trusted_review_confirmed": True,
    }
    value.update(changes)
    return value


def delta(**changes):
    value = {
        "candidate_sha256": SHA["candidate"], "public_id": PUBLIC_ID,
        "before_total": 867, "before_enabled": 0, "before_eligible": 0,
        "matched_row_count": 1, "affected_row_count": 1,
        "after_total": 867, "after_enabled": 1, "after_eligible": 1,
        "eligible_id_matches": True,
    }
    value.update(changes)
    return value


class ScopedOneCtaGateTests(unittest.TestCase):
    def assert_inert(self, result):
        for name in ("production_activation_allowed", "publication_allowed",
                     "affiliate_eligibility_allowed", "gate_mutation_allowed",
                     "d1_write_allowed", "route_activation_allowed",
                     "api_request_allowed"):
            self.assertFalse(getattr(result, name), name)

    def test_exact_review_is_ready_but_inert_and_unguaranteed(self):
        result = subject.evaluate_cta(evidence(), anchors(), now=NOW)
        self.assertEqual(result.status, subject.READY)
        self.assertTrue(result.review_ready)
        self.assertTrue(result.route_smoke_required)
        self.assertTrue(result.outcome_verification_required)
        self.assert_inert(result)

    def test_each_bound_scope_or_freshness_change_blocks(self):
        cases = (
            ({"official_response_status": "LINK_ALLOWED"}, {}),
            ({"official_response_sha256": "0" * 64}, {}),
            ({"candidate_sha256": "8" * 64}, {}),
            ({"surface": "/other/"}, {}), ({"route_prefix": "/out/"}, {}),
            ({"public_id": "internal"}, {}), ({"cta_count": 2}, {}),
            ({"item_count": 99}, {}),
            ({"compliance_candidate_sha256": SHA["source"]}, {}),
            ({"user_candidate_sha256": SHA["source"]}, {}),
            ({"valid_until": "2026-09-29T02:59:59Z"}, {}),
            ({"free_confirmed_at": "2026-09-28T02:59:59Z"}, {}),
            ({}, {"trusted_review_confirmed": False}),
            ({}, {"rollback_worker_version": "other"}),
        )
        for evidence_change, anchor_change in cases:
            with self.subTest(e=evidence_change, a=anchor_change):
                result = subject.evaluate_cta(
                    evidence(**evidence_change), anchors(**anchor_change), now=NOW)
                self.assertEqual(result.status, subject.BLOCKED)
                self.assertFalse(result.review_ready)
                self.assert_inert(result)

    def test_unknown_fields_and_type_confusion_block(self):
        self.assertEqual(subject.evaluate_cta({**evidence(), "secret": "x"}, anchors(), now=NOW).status, subject.BLOCKED)
        self.assertEqual(subject.evaluate_cta(evidence(cta_count=True), anchors(), now=NOW).status, subject.BLOCKED)

    def test_exact_zero_to_one_delta_is_review_only(self):
        result = subject.evaluate_one_row_delta(delta(), evidence(), anchors(), now=NOW)
        self.assertEqual(result.status, subject.DELTA_READY)
        self.assertTrue(result.review_ready)
        self.assert_inert(result)

    def test_all_delta_drifts_block(self):
        for change in (
            {"before_total": 866}, {"before_enabled": 1},
            {"before_eligible": 1}, {"matched_row_count": 2},
            {"affected_row_count": 0}, {"affected_row_count": 2},
            {"after_total": 868}, {"after_enabled": 2},
            {"after_eligible": 0}, {"after_eligible": 2},
            {"eligible_id_matches": False}, {"changed_rows": 1},
        ):
            with self.subTest(change=change):
                result = subject.evaluate_one_row_delta(delta(**change), evidence(), anchors(), now=NOW)
                self.assertEqual(result.status, subject.DELTA_BLOCKED)
                self.assertFalse(result.review_ready)
                self.assert_inert(result)


if __name__ == "__main__":
    unittest.main()
