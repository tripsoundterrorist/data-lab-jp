from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import collection_policy  # noqa: E402
import revenue_mvp_ranking_readiness as subject  # noqa: E402


def evidence(**changes):
    values = {field: False for field in subject.RankingEvidence.__dataclass_fields__}
    values.update(changes)
    return subject.RankingEvidence(**values)


class RankingReadinessTests(unittest.TestCase):
    def test_current_state_is_blocked_without_publication_or_writes(self):
        result = subject.assess(subject.current_evidence())
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertFalse(result.implementation_review_candidate)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_write_allowed)
        self.assertFalse(result.ranking_label_allowed)
        self.assertIn("OFFICIAL_SORT_DEFINITION_UNCONFIRMED", result.reason_codes)
        self.assertIn("RANK_COLLECTION_NOT_PRODUCTION_ELIGIBLE", result.reason_codes)

    def test_price_and_observation_sorts_remain_safe(self):
        result = subject.assess(subject.current_evidence())
        self.assertEqual(result.safe_existing_sorts, subject.SAFE_EXISTING_SORTS)
        self.assertNotIn("rank", result.safe_existing_sorts)

    def test_unsubstantiated_ranking_labels_are_explicitly_prohibited(self):
        result = subject.assess(subject.current_evidence())
        for label in ("人気ランキング", "売れ筋ランキング", "公式ランキング"):
            self.assertIn(label, result.prohibited_public_labels)

    def test_complete_input_still_respects_collection_policy_gate(self):
        complete = evidence(**{
            field: True for field in subject.RankingEvidence.__dataclass_fields__
        })
        result = subject.assess(complete)
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertIn("RANK_COLLECTION_NOT_PRODUCTION_ELIGIBLE", result.reason_codes)

    def test_future_eligible_policy_reaches_review_only(self):
        complete = evidence(**{
            field: True for field in subject.RankingEvidence.__dataclass_fields__
        })
        policy_result = collection_policy.PolicyEvaluation(
            True, True, (), 2, 200,
        )
        with mock.patch.object(
            subject.collection_policy, "evaluate_collection_policy", return_value=policy_result
        ):
            result = subject.assess(complete)
        self.assertEqual(result.status, subject.READY_FOR_MANUAL_IMPLEMENTATION_REVIEW)
        self.assertTrue(result.implementation_review_candidate)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_write_allowed)

    def test_invalid_evidence_and_internal_error_fail_closed(self):
        self.assertEqual(subject.assess({}).status, subject.FAIL_CLOSED)
        with mock.patch.object(
            subject.collection_policy, "rank_candidate_policy", side_effect=RuntimeError
        ):
            self.assertEqual(subject.assess(subject.current_evidence()).status, subject.FAIL_CLOSED)


if __name__ == "__main__":
    unittest.main()
