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
import temporal_isolated_collector_response_bridge as bridge  # noqa: E402
from temporal_runbook_policy import FIXED_POPULATIONS  # noqa: E402


BASE = datetime(2026, 9, 13, tzinfo=timezone.utc)
AS_OF = BASE + timedelta(hours=1)


def response(identity, *, success=True, error=None):
    return {
        "request": {
            "source_sort": identity[0], "offset": identity[1], "hits": identity[2]
        },
        "success": success,
        "result_count": 1 if success else 0,
        "items": [{"content_id": f"private-{identity[0]}-{identity[1]}"}]
        if success else [],
        "error_classification": error,
    }


def approval():
    return connection.ActiveRunnerConnectionApproval(
        connection.APPROVAL_VERSION, connection.APPROVAL_SCOPE, True
    )


def mappings(value):
    return {identity: value for identity in FIXED_POPULATIONS}


class IsolatedCollectorResponseBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = filesystem.IsolatedTemporalStateStore.for_test(self.root)
        self.fetcher = mock.Mock(side_effect=lambda identity: response(identity))
        self.delay = mock.Mock()
        self.subject = bridge.IsolatedCollectorResponseBridge.for_test(
            fetcher=self.fetcher, delay=self.delay
        )

    def execute(self, **overrides):
        values = {
            "approval": approval(),
            "series_id": "series-20260913T000000Z-a1b2c3d4",
            "captured_at": BASE,
            "as_of": AS_OF,
            "documents_by_population": mappings(()),
            "history_counts": mappings(0),
            "store": self.store,
        }
        values.update(overrides)
        return self.subject.run(**values)

    def test_four_fixture_responses_connect_only_after_atomic_validation(self):
        result = self.execute()
        self.assertEqual(result.status, bridge.COMPLETE)
        self.assertEqual((result.attempted_request_count,
                          result.validated_response_count), (4, 4))
        self.assertEqual((result.assessed_population_count,
                          result.persisted_population_count), (4, 4))
        self.assertTrue(result.active_runner_connected)
        self.assertEqual(self.fetcher.call_count, 4)
        self.assertEqual(self.delay.call_args_list, [mock.call(1.0)] * 3)
        self.assertFalse(result.live_api_authorized)
        self.assertFalse(result.scheduler_change_authorized)
        self.assertFalse(result.production_write_authorized)
        self.assertFalse(result.deploy_allowed)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.affiliate_activation_allowed)

    def test_rate_limit_stops_without_retry_or_state_write(self):
        self.fetcher.side_effect = [
            response(FIXED_POPULATIONS[0]),
            response(FIXED_POPULATIONS[1], success=False, error="RATE_LIMIT"),
        ]
        result = self.execute()
        self.assertEqual(result.status, bridge.BLOCKED)
        self.assertEqual(result.reason_codes, ("RATE_LIMIT",))
        self.assertEqual(result.attempted_request_count, 2)
        self.assertEqual(self.fetcher.call_count, 2)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_malformed_fourth_response_blocks_before_any_state_write(self):
        values = [response(identity) for identity in FIXED_POPULATIONS]
        values[-1]["raw_url"] = "https://not-accepted.invalid"
        self.fetcher.side_effect = values
        result = self.execute()
        self.assertEqual(result.status, bridge.BLOCKED)
        self.assertFalse(result.filesystem_access_performed)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_request_identity_mismatch_fails_closed(self):
        wrong = response(FIXED_POPULATIONS[0])
        wrong["request"]["offset"] = 999
        self.fetcher.side_effect = [wrong]
        result = self.execute()
        self.assertEqual(result.status, bridge.BLOCKED)
        self.assertEqual(result.validated_response_count, 0)

    def test_invalid_interval_blocks_before_fetch(self):
        for value in (0, 0.5, True, 61):
            with self.subTest(value=value):
                result = self.execute(request_interval_seconds=value)
                self.assertEqual(result.status, bridge.BLOCKED)
        self.fetcher.assert_not_called()

    def test_live_construction_is_unavailable(self):
        with self.assertRaises(ValueError):
            bridge.IsolatedCollectorResponseBridge(self.fetcher, self.delay, object())

    def test_safe_result_exposes_no_identifiers_or_paths(self):
        rendered = json.dumps(self.execute().to_dict()).casefold()
        for forbidden in ("private-", "series-", str(self.root).casefold(), "content_id"):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
