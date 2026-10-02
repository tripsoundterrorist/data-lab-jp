from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ebook_comic_review_pair_policy_candidate as subject  # noqa: E402


class EbookComicReviewPairPolicyCandidateTests(unittest.TestCase):
    def assert_closed(self, result):
        self.assertFalse(result.source_history_mutation_allowed)
        self.assertFalse(result.inferred_value_allowed)
        self.assertFalse(result.compliance_approved)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_write_allowed)

    def test_complete_pair_is_preserved_only_as_non_public_candidate(self):
        result = subject.assess(4.5, 10)
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.source_state, "COMPLETE")
        self.assertEqual(result.projection_action, subject.PRESERVE_COMPLETE)
        self.assert_closed(result)

    def test_absent_pair_is_omitted_without_inference(self):
        result = subject.assess(None, None)
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.source_state, "ABSENT")
        self.assertEqual(result.projection_action, subject.OMIT_ABSENT)
        self.assert_closed(result)

    def test_each_incomplete_direction_is_omitted_without_source_mutation(self):
        for average, count in ((None, 3), (4.0, None)):
            with self.subTest(average=average, count=count):
                result = subject.assess(average, count)
                self.assertEqual(result.status, subject.READY)
                self.assertEqual(result.source_state, "INCOMPLETE")
                self.assertEqual(result.projection_action, subject.OMIT_INCOMPLETE)
                self.assertIn("SOURCE_HISTORY_PRESERVED", result.reason_codes)
                self.assert_closed(result)

    def test_invalid_values_fail_closed(self):
        for average, count in ((-1, 1), (float("nan"), 1), (4.0, -1), (None, True)):
            with self.subTest(average=average, count=count):
                result = subject.assess(average, count)
                self.assertEqual(result.status, subject.FAIL_CLOSED)
                self.assertEqual(result.projection_action, subject.BLOCK_INVALID)
                self.assert_closed(result)


if __name__ == "__main__":
    unittest.main()
