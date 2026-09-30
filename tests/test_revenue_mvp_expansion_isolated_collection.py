from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_expansion_isolated_collection as subject  # noqa: E402


NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


class IsolatedCollectionTests(unittest.TestCase):
    def test_missing_inputs_block_without_api_or_write(self):
        result = subject.assess(Path("missing.db"), Path("missing.env"), evaluated_at=NOW)
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertEqual(result.api_calls, 0)
        self.assertFalse(result.production_database_write_performed)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.collection_only_storage_committed)
        self.assertIsNone(result.retained_sha256)

    def test_naive_time_blocks_before_loading_collector(self):
        with mock.patch.object(subject, "_load_collector") as loader:
            result = subject.assess(ROOT / "data" / "data-lab.db", ROOT / ".env", evaluated_at=datetime(2026, 10, 1))
        self.assertEqual(result.status, subject.BLOCKED)
        loader.assert_not_called()

    def test_collector_failure_is_bounded_and_source_unchanged(self):
        source = ROOT / "data" / "data-lab.db"
        before = subject._sha256(source)
        with mock.patch.object(subject, "_run_collector", return_value=7):
            result = subject.assess(source, ROOT / ".env", evaluated_at=NOW)
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertEqual(subject._sha256(source), before)
        self.assertFalse(result.temporary_database_retained)
        self.assertFalse(result.production_database_write_performed)

    def test_invalid_retention_root_blocks_before_collector_load(self):
        with mock.patch.object(subject, "_load_collector") as loader:
            result = subject.assess(
                ROOT / "data" / "data-lab.db",
                ROOT / ".env",
                evaluated_at=NOW,
                retain_private_root=ROOT / "data",
            )
        # The input database copy is allowed, but an actual collector must not
        # run when the retention destination is outside runtime/private.
        self.assertEqual(result.status, subject.BLOCKED)
        loader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
