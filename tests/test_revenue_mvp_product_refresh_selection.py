from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_product_refresh_selection as subject  # noqa: E402


def page(start: int, count: int = 100) -> bytes:
    return "".join(
        f'<a href="/go/itm_{value:024x}">item</a>'
        for value in range(start, start + count)
    ).encode("ascii")


class ProductRefreshSelectionTests(unittest.TestCase):
    def test_exact_delta_builds_four_bounded_batches_without_exposing_ids(self):
        source = page(0)
        candidate = page(18)
        result, payload = subject.build(source, candidate, batch_index=0)
        self.assertEqual(result.status, subject.READY)
        self.assertEqual((result.added_count, result.removed_count), (18, 18))
        self.assertEqual((result.selected_count, result.batch_count), (5, 4))
        self.assertFalse(result.identifiers_exposed)
        self.assertFalse(result.api_request_performed)
        self.assertFalse(result.d1_write_performed)
        self.assertFalse(result.publication_allowed)
        self.assertIsNotNone(payload)
        self.assertEqual(len(payload.splitlines()), 5)

    def test_last_batch_contains_only_three_ids(self):
        result, payload = subject.build(page(0), page(18), batch_index=3)
        self.assertEqual(result.status, subject.READY)
        self.assertEqual(result.selected_count, 3)
        self.assertEqual(len(payload.splitlines()), 3)

    def test_invalid_delta_and_out_of_range_batch_fail_closed(self):
        for candidate, batch_index, reason in (
            (page(1), 0, "REFRESH_DELTA_INVALID"),
            (page(18), 4, "BATCH_INDEX_OUT_OF_RANGE"),
        ):
            with self.subTest(reason=reason):
                result, payload = subject.build(
                    page(0), candidate, batch_index=batch_index,
                )
                self.assertEqual(result.status, subject.BLOCKED)
                self.assertIn(reason, result.reason_codes)
                self.assertIsNone(payload)

    def test_write_requires_output_outside_repository_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.html"
            candidate = root / "candidate.html"
            output = root / "selection.txt"
            source.write_bytes(page(0))
            candidate.write_bytes(page(18))
            result = subject.write(source, candidate, output, batch_index=0)
            self.assertEqual(result.status, subject.READY)
            self.assertTrue(result.output_written)
            self.assertEqual(len(output.read_text(encoding="ascii").splitlines()), 5)
            blocked = subject.write(source, candidate, output, batch_index=0)
            self.assertEqual(blocked.status, subject.BLOCKED)
            self.assertIn("PATH_BOUNDARY_INVALID", blocked.reason_codes)


if __name__ == "__main__":
    unittest.main()
