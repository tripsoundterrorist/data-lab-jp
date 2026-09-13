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
import temporal_approved_active_runner_connection as connection  # noqa: E402
import temporal_filesystem_persistence_candidate as filesystem  # noqa: E402
import temporal_probe_series_integration_adapter as adapter  # noqa: E402
from temporal_runbook_policy import FIXED_POPULATIONS  # noqa: E402


BASE = datetime(2026, 9, 13, tzinfo=timezone.utc)
AS_OF = BASE + timedelta(hours=1)


def approval(granted=True):
    return connection.ActiveRunnerConnectionApproval(
        connection.APPROVAL_VERSION, connection.APPROVAL_SCOPE, granted
    )


def bundle():
    payloads = [
        {
            "source_sort": source_sort,
            "offset": offset,
            "hits": hits,
            "result_count": 1,
            "items": [{"content_id": f"private-{source_sort}-{offset}"}],
        }
        for source_sort, offset, hits in FIXED_POPULATIONS
    ]
    return adapter.build_validated_series_state_bundle(
        series_id="series-20260913T000000Z-a1b2c3d4",
        captured_at=BASE,
        as_of=AS_OF,
        payloads=payloads,
    )


def mappings(value):
    return {identity: value for identity in FIXED_POPULATIONS}


class ApprovedActiveRunnerConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = filesystem.IsolatedTemporalStateStore.for_test(self.root)

    def execute(self, *, approved=True, value=None, store=None):
        return connection.connect_approved_isolated_active_runner(
            approval=approval(approved),
            bundle=value or bundle(),
            documents_by_population=mappings(()),
            history_counts=mappings(0),
            store=store or self.store,
            as_of=AS_OF,
        )

    def test_exact_approval_connects_only_to_isolated_store(self):
        result = self.execute()
        self.assertEqual(result.status, connection.CONNECTED)
        self.assertTrue(result.success)
        self.assertTrue(result.approval_verified)
        self.assertTrue(result.review_verified)
        self.assertTrue(result.active_runner_connected)
        self.assertEqual((result.assessed_population_count,
                          result.persisted_population_count), (4, 4))
        self.assertEqual(len(list(self.root.glob("*.json"))), 4)
        self.assertFalse(result.api_request_authorized)
        self.assertFalse(result.scheduler_change_authorized)
        self.assertFalse(result.production_write_authorized)
        self.assertFalse(result.deploy_allowed)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.affiliate_activation_allowed)

    def test_missing_or_wrong_approval_blocks_before_filesystem_access(self):
        values = (
            approval(False),
            replace(approval(), version="invalid"),
            replace(approval(), scope="PRODUCTION"),
            object(),
        )
        for value in values:
            with self.subTest(value=value):
                result = connection.connect_approved_isolated_active_runner(
                    approval=value, bundle=bundle(),
                    documents_by_population=mappings(()),
                    history_counts=mappings(0), store=self.store, as_of=AS_OF,
                )
                self.assertEqual(result.status, connection.BLOCKED)
                self.assertFalse(result.filesystem_access_performed)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_review_failure_blocks_before_candidate_call(self):
        changed = mock.Mock(status=connection.review.BLOCKED)
        with mock.patch.object(
            connection.review, "review_active_runner_connection", return_value=changed
        ), mock.patch.object(
            connection.candidate, "run_isolated_active_runner_candidate"
        ) as run:
            result = self.execute()
        self.assertEqual(result.status, connection.BLOCKED)
        run.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_invalid_bundle_fails_closed_without_connection(self):
        result = self.execute(value=replace(bundle(), success=False))
        self.assertEqual(result.status, connection.BLOCKED)
        self.assertFalse(result.active_runner_connected)

    def test_non_isolated_store_is_rejected(self):
        result = self.execute(store=object())
        self.assertEqual(result.status, connection.BLOCKED)
        self.assertFalse(result.filesystem_access_performed)

    def test_result_does_not_expose_identifiers_or_paths(self):
        rendered = json.dumps(self.execute().to_dict()).casefold()
        for forbidden in ("private-", "series-", str(self.root).casefold(), "content_id"):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
