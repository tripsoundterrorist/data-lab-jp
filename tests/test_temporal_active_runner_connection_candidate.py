from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import temporal_active_runner_connection_candidate as candidate  # noqa: E402
import temporal_filesystem_persistence_candidate as filesystem  # noqa: E402
import temporal_probe_series_integration_adapter as adapter  # noqa: E402
from temporal_runbook_policy import FIXED_POPULATIONS  # noqa: E402

BASE = datetime(2026, 9, 12, tzinfo=timezone.utc)
AS_OF = BASE + timedelta(hours=1)


def bundle():
    payloads = [
        {"source_sort": sort, "offset": offset, "hits": hits,
         "result_count": 1,
         "items": [{"content_id": f"private-{sort}-{offset}"}]}
        for sort, offset, hits in FIXED_POPULATIONS
    ]
    return adapter.build_validated_series_state_bundle(
        series_id="series-20260912T000000Z-a1b2c3d4",
        captured_at=BASE, as_of=AS_OF, payloads=payloads,
    )


def mappings(value):
    return {identity: value for identity in FIXED_POPULATIONS}


class ActiveRunnerConnectionCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = filesystem.IsolatedTemporalStateStore.for_test(self.root)

    def execute(self, value=None, histories=None):
        return candidate.run_isolated_active_runner_candidate(
            bundle=value or bundle(), documents_by_population=mappings(()),
            history_counts=histories or mappings(0), store=self.store, as_of=AS_OF,
        )

    def test_valid_bundle_assesses_then_persists_four_test_files(self):
        result = self.execute()
        self.assertEqual(result.status, candidate.COMPLETE)
        self.assertEqual((result.assessed_population_count,
                          result.persisted_population_count), (4, 4))
        self.assertEqual(len(list(self.root.glob("*.json"))), 4)
        self.assertTrue(result.filesystem_access_performed)
        self.assertFalse(result.active_runner_connected)
        self.assertFalse(result.legacy_runner_used)
        self.assertFalse(result.api_request_authorized)
        self.assertFalse(result.production_write_authorized)
        self.assertFalse(result.scheduler_change_authorized)
        self.assertFalse(result.deploy_allowed)

    def test_invalid_bundle_stops_before_persistence_and_io(self):
        result = self.execute(replace(bundle(), success=False))
        self.assertEqual(result.status, candidate.BLOCKED)
        self.assertFalse(result.filesystem_access_performed)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_dry_assessment_failure_never_calls_persistence(self):
        histories = mappings(0)
        histories[FIXED_POPULATIONS[0]] = 1
        with mock.patch.object(
            candidate.persistence, "persist_validated_bundle_for_test"
        ) as persist:
            result = self.execute(histories=histories)
        self.assertEqual(result.status, candidate.BLOCKED)
        persist.assert_not_called()

    def test_non_test_store_is_blocked_without_access(self):
        result = candidate.run_isolated_active_runner_candidate(
            bundle=bundle(), documents_by_population=mappings(()),
            history_counts=mappings(0), store=object(), as_of=AS_OF,
        )
        self.assertEqual(result.status, candidate.BLOCKED)
        self.assertFalse(result.filesystem_access_performed)

    def test_safe_result_contains_no_identifiers_or_paths(self):
        rendered = json.dumps(self.execute().to_dict()).casefold()
        for forbidden in ("private-", "series-", str(self.root).casefold(), "content_id"):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
