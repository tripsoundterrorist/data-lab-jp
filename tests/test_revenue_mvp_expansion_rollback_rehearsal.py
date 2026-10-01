from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_expansion_rollback_rehearsal as subject  # noqa: E402


class ExpansionRollbackRehearsalTests(unittest.TestCase):
    def test_current_surface_restores_byte_exact_in_isolation(self):
        result = subject.rehearse()
        self.assertEqual(result.status, subject.VERIFIED)
        self.assertEqual(result.source_file_count, 21)
        self.assertEqual(result.source_item_count, 100)
        self.assertEqual(len(result.source_snapshot_sha256 or ""), 64)
        self.assertTrue(result.candidate_differed_from_source)
        self.assertTrue(result.restore_byte_exact)
        self.assertTrue(result.repeated_restore_deterministic)
        self.assertTrue(result.source_unchanged)
        self.assertTrue(result.rollback_plan_verified)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.deployment_allowed)
        self.assertFalse(result.external_io_performed)

    def test_changed_item_count_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            replica = Path(directory) / "repo"
            replica.mkdir()
            builder = subject._load_builder()
            for name in builder.ALLOWLIST:
                destination = replica / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, destination)
            listing = replica / "items" / "index.html"
            listing.write_text(
                listing.read_text(encoding="utf-8").replace(
                    '<article class="item">', '<section class="item">', 1
                ),
                encoding="utf-8",
            )
            result = subject.rehearse(replica)
        self.assertEqual(result.status, subject.FAIL_CLOSED)
        self.assertIn("CURRENT_ITEM_COUNT_NOT_EXACT", result.reason_codes)

    def test_missing_source_fails_closed_without_details(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subject.rehearse(Path(directory))
        self.assertEqual(result.status, subject.FAIL_CLOSED)
        self.assertEqual(result.reason_codes, ("ROLLBACK_REHEARSAL_INTERNAL_ERROR",))
        self.assertIsNone(result.source_snapshot_sha256)


if __name__ == "__main__":
    unittest.main()
