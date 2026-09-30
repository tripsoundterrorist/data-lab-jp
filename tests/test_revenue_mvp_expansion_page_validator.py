from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_expansion_page_validator as subject  # noqa: E402


def pages():
    return tuple(
        subject.PageObservation(
            offset=offset,
            requested_hits=50,
            result_count=50,
            content_ids=tuple(f"content-{offset + index}" for index in range(50)),
        )
        for offset in subject.EXPECTED_OFFSETS
    )


class ExpansionPageValidatorTests(unittest.TestCase):
    def test_exact_six_non_overlapping_pages_pass(self):
        result = subject.validate(pages())
        self.assertEqual(result.status, subject.PASS)
        self.assertEqual(result.item_count, 300)
        self.assertEqual(result.unique_item_count, 300)
        self.assertTrue(result.database_write_allowed)

    def test_missing_page_blocks(self):
        result = subject.validate(pages()[:-1])
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertIn("PAGE_COUNT_NOT_EXACT", result.reason_codes)
        self.assertFalse(result.database_write_allowed)

    def test_offset_gap_blocks(self):
        values = list(pages())
        values[2] = subject.PageObservation(102, 50, 50, values[2].content_ids)
        result = subject.validate(tuple(values))
        self.assertIn("OFFSET_SEQUENCE_INVALID", result.reason_codes)

    def test_duplicate_across_pages_blocks(self):
        values = list(pages())
        duplicate = (values[0].content_ids[0],) + values[-1].content_ids[1:]
        values[-1] = subject.PageObservation(251, 50, 50, duplicate)
        result = subject.validate(tuple(values))
        self.assertIn("DUPLICATE_CONTENT_ID_ACROSS_PAGES", result.reason_codes)
        self.assertFalse(result.database_write_allowed)

    def test_short_page_blocks(self):
        values = list(pages())
        values[-1] = subject.PageObservation(251, 50, 49, values[-1].content_ids[:-1])
        result = subject.validate(tuple(values))
        self.assertIn("PAGE_RESULT_COUNT_NOT_EXACT", result.reason_codes)
        self.assertIn("TOTAL_ITEM_COUNT_NOT_EXACT", result.reason_codes)

    def test_invalid_contract_blocks(self):
        result = subject.validate([])
        self.assertEqual(result.reason_codes, ("PAGE_CONTRACT_INVALID",))


if __name__ == "__main__":
    unittest.main()
