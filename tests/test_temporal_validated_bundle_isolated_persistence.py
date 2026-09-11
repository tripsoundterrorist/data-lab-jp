from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import temporal_filesystem_persistence_candidate as filesystem  # noqa: E402
import temporal_probe_series_integration_adapter as adapter  # noqa: E402
import temporal_validated_bundle_isolated_persistence as connection  # noqa: E402
from temporal_runbook_policy import FIXED_POPULATIONS  # noqa: E402

BASE = datetime(2026, 9, 11, tzinfo=timezone.utc)
AS_OF = BASE + timedelta(hours=1)


def bundle():
    payloads = [{"source_sort": s, "offset": o, "hits": h, "result_count": 1,
                 "items": [{"content_id": f"private-{s}-{o}"}]}
                for s, o, h in FIXED_POPULATIONS]
    return adapter.build_validated_series_state_bundle(
        series_id="series-20260911T000000Z-a1b2c3d4",
        captured_at=BASE, as_of=AS_OF, payloads=payloads)


class IsolatedBundlePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = filesystem.IsolatedTemporalStateStore.for_test(self.root)

    def test_exact_bundle_persists_four_files_without_production_authority(self):
        result = connection.persist_validated_bundle_for_test(
            bundle(), store=self.store, as_of=AS_OF)
        self.assertEqual(result.status, "ISOLATED_BUNDLE_PERSISTED")
        self.assertEqual(result.persisted_count, 4)
        self.assertEqual(len(list(self.root.glob("*.json"))), 4)
        self.assertFalse(result.active_pipeline_connected)
        self.assertFalse(result.production_write_authorized)

    def test_invalid_bundle_blocks_before_access(self):
        result = connection.persist_validated_bundle_for_test(
            replace(bundle(), success=False), store=self.store, as_of=AS_OF)
        self.assertEqual(result.status, "PERSISTENCE_BLOCKED")
        self.assertFalse(result.filesystem_access_performed)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_replay_is_noop_and_safe_result_contains_no_private_values(self):
        first = connection.persist_validated_bundle_for_test(
            bundle(), store=self.store, as_of=AS_OF)
        second = connection.persist_validated_bundle_for_test(
            bundle(), store=self.store, as_of=AS_OF)
        self.assertEqual(first.persisted_count, 4)
        self.assertEqual(second.persisted_count, 0)
        self.assertNotIn("private", repr(second))


if __name__ == "__main__":
    unittest.main()
