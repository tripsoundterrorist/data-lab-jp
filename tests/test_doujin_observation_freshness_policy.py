from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import doujin_observation_freshness_policy as subject  # noqa: E402


NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


def iso(value: datetime) -> str:
    return value.isoformat()


class DoujinObservationFreshnessPolicyTests(unittest.TestCase):
    def test_current_observation_uses_nonofficial_label(self):
        result = subject.evaluate(observed_at=iso(NOW), evaluated_at=iso(NOW))
        self.assertEqual(result.status, subject.CURRENT)
        self.assertEqual(result.observation_label, "DATA LAB確認日時")
        self.assertTrue(result.display_candidate)
        self.assertFalse(result.official_update_claim_allowed)
        self.assertFalse(result.realtime_claim_allowed)
        self.assertFalse(result.publication_allowed)

    def test_exact_collection_health_boundary_is_current(self):
        observed = NOW - timedelta(seconds=subject.collection_health.MAX_AGE_SECONDS)
        result = subject.evaluate(observed_at=iso(observed), evaluated_at=iso(NOW))
        self.assertEqual(result.status, subject.CURRENT)

    def test_one_second_past_boundary_is_stale_and_hidden(self):
        observed = NOW - timedelta(seconds=subject.collection_health.MAX_AGE_SECONDS + 1)
        result = subject.evaluate(observed_at=iso(observed), evaluated_at=iso(NOW))
        self.assertEqual(result.status, subject.STALE)
        self.assertFalse(result.display_candidate)
        self.assertFalse(result.publication_allowed)

    def test_future_or_naive_timestamp_fails_closed(self):
        future = subject.evaluate(
            observed_at=iso(NOW + timedelta(seconds=1)), evaluated_at=iso(NOW)
        )
        self.assertEqual(future.status, subject.FAIL_CLOSED)
        naive = subject.evaluate(observed_at="2026-10-02T12:00:00", evaluated_at=iso(NOW))
        self.assertEqual(naive.status, subject.FAIL_CLOSED)


if __name__ == "__main__":
    unittest.main()
