from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import json
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_temporal_continuation_assessment as assessment  # noqa: E402


AS_OF = datetime(2026, 9, 9, tzinfo=timezone.utc)


def states(age_hours: float):
    captured_at = AS_OF - timedelta(hours=age_hours)
    return tuple(
        SimpleNamespace(
            population_identity=(
                assessment.SITE,
                assessment.SERVICE,
                assessment.FLOOR,
                source_sort,
                offset,
                hits,
            ),
            captured_at=captured_at,
        )
        for source_sort, offset, hits in assessment.FIXED_POPULATIONS
    )


class TemporalContinuationAssessmentTests(unittest.TestCase):
    def assess(self, values):
        with mock.patch.object(
            assessment.temporal_probe_state_store,
            "discover_valid_states",
            return_value=values,
        ):
            return assessment.assess_temporal_continuation(as_of=AS_OF)

    def test_long_gap_blocks_before_api_or_state_write(self):
        result = self.assess(states(49))
        self.assertEqual(result.status, assessment.LONG_GAP_BLOCKED)
        self.assertTrue(result.fresh_baseline_policy_required)
        self.assertFalse(result.api_request_authorized)
        self.assertFalse(result.state_write_authorized)

    def test_valid_window_is_candidate_not_authorization(self):
        result = self.assess(states(24))
        self.assertEqual(result.status, assessment.WINDOW_CANDIDATE)
        self.assertTrue(result.observation_window_candidate)
        self.assertFalse(result.api_request_authorized)
        self.assertFalse(result.state_write_authorized)

    def test_too_soon_waits(self):
        result = self.assess(states(6))
        self.assertEqual(result.status, assessment.WAIT)
        self.assertFalse(result.observation_window_candidate)

    def test_missing_population_fails_closed(self):
        result = self.assess(states(24)[:-1])
        self.assertEqual(result.status, assessment.FAIL_CLOSED)
        self.assertEqual(result.populations_found, 3)

    def test_mixed_windows_fail_closed(self):
        values = list(states(24))
        values[-1].captured_at = AS_OF - timedelta(hours=60)
        result = self.assess(tuple(values))
        self.assertEqual(result.status, assessment.FAIL_CLOSED)
        self.assertIn("POPULATION_WINDOWS_INCONSISTENT", result.reason_codes)

    def test_internal_detail_is_not_returned(self):
        with mock.patch.object(
            assessment.temporal_probe_state_store,
            "discover_valid_states",
            side_effect=RuntimeError("secret path detail"),
        ):
            result = assessment.assess_temporal_continuation(as_of=AS_OF)
        serialized = json.dumps(result.to_dict())
        self.assertEqual(result.status, assessment.FAIL_CLOSED)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("path", serialized)

    def test_source_has_no_mutation_or_external_io(self):
        source = Path(assessment.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "write_temporal_probe_state", "urllib", "requests", "subprocess",
            "INSERT", "UPDATE", "DELETE", "fetch(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
