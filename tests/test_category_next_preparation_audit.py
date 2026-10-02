from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import category_collection_value_audit as values  # noqa: E402
import category_next_preparation_audit as subject  # noqa: E402


def category(content_type: str, items: int, *, genre: int | None = None):
    complete = items
    return values.CategoryAggregate(
        content_type,
        items,
        items * 2,
        22,
        "2026-09-01T00:00:00Z",
        "2026-10-02T00:00:00Z",
        complete,
        complete,
        complete,
        complete if genre is None else genre,
        complete,
        0,
        0,
        0,
        0,
    )


def audit(rows):
    return values.CategoryValueAudit(
        values.VERSION,
        values.READY,
        len(rows),
        sum(row.item_count for row in rows),
        sum(row.snapshot_count for row in rows),
        tuple(rows),
        True,
        False,
        False,
        ("FIXTURE",),
    )


class CategoryNextPreparationAuditTests(unittest.TestCase):
    def test_largest_eligible_non_doujin_category_is_recommended(self):
        result = subject.compose(
            audit(
                (
                    category("doujin", 950),
                    category("ebook_comic", 558),
                    category("photo_book", 263),
                    category("pc_game", 74),
                )
            )
        )
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.recommended_content_type, "ebook_comic")
        self.assertEqual(result.candidate_count, 2)
        self.assertFalse(result.revenue_priority_confirmed)
        self.assertFalse(result.compliance_approved)
        self.assertFalse(result.publication_allowed)

    def test_metadata_gap_blocks_technical_candidate(self):
        result = subject.compose(audit((category("ebook_novel", 200, genre=100),)))
        self.assertIsNone(result.recommended_content_type)
        self.assertEqual(result.candidate_count, 0)
        self.assertIn(
            "CORE_METADATA_COVERAGE_BELOW_THRESHOLD",
            result.candidates[0].reason_codes,
        )

    def test_nonready_or_wrong_contract_fails_closed(self):
        failed = values.CategoryValueAudit(
            values.VERSION,
            values.FAIL_CLOSED,
            0,
            0,
            0,
            (),
            False,
            False,
            False,
            ("FAIL",),
        )
        for value in ({}, failed):
            with self.subTest(value=value):
                result = subject.compose(value)
                self.assertEqual(result.status, subject.FAIL_CLOSED)
                self.assertFalse(result.publication_allowed)


if __name__ == "__main__":
    unittest.main()
