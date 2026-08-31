from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import development_fresh_usage_protected_start_adapter as adapter  # noqa: E402
import development_gate_coordinator as coordinator  # noqa: E402
import development_gate_evidence as gate_core  # noqa: E402
import development_usage_evidence_freshness as freshness  # noqa: E402


NOW = 2_000_000_000
CHECKPOINT = "a" * 64
SHA = "b" * 40


def ready_gate():
    return gate_core.DevelopmentGateEvidence(
        "current-gate", "next-gate", checkpoint_status="SAVED",
        checkpoint_ref=CHECKPOINT, test_tier="REGRESSION",
        test_status="PASSED", commit_sha=SHA, pushed_sha=SHA,
        ci_status="SUCCESS", ci_head_sha=SHA, ci_run_id=46,
        approval_status="APPROVED",
    )


def snapshot(**changes):
    values = {
        "snapshot_version": freshness.SNAPSHOT_VERSION,
        "source": freshness.TRUSTED_SOURCE,
        "observed_at_epoch_s": NOW,
        "five_hour_remaining_pct": 86,
        "weekly_remaining_pct": 74,
        "task_size": "SMALL",
        "operational_reserve_protected": True,
    }
    values.update(changes)
    return freshness.UsageEvidenceSnapshot(**values)


def action(status=coordinator.ACTION_SUCCEEDED,
           reasons=("START_CONFIRMED",)):
    return coordinator.DevelopmentGateActionResult(
        coordinator.ACTION_RESULT_VERSION, "START_NEXT_GATE", status, None,
        reasons,
    )


def enabled(downstream, usage_snapshot=None, evaluated=NOW):
    return adapter.FreshUsageProtectedStartAdapter._for_test(
        downstream,
        usage_snapshot if usage_snapshot is not None else snapshot(),
        evaluated_at_epoch_s=evaluated,
    )


class DevelopmentFreshUsageProtectedStartAdapterTests(unittest.TestCase):
    def test_fresh_permitted_snapshot_invokes_downstream_once(self):
        downstream = mock.Mock(return_value=action())
        result = coordinator.DevelopmentGateCoordinator._for_test({
            "START_NEXT_GATE": enabled(downstream),
        }).coordinate(ready_gate())
        self.assertEqual(result.status, "NEXT_GATE_STARTED")
        downstream.assert_called_once_with(ready_gate())

    def test_stale_snapshot_blocks_before_usage_and_downstream(self):
        downstream = mock.Mock(return_value=action())
        stale = snapshot(
            observed_at_epoch_s=NOW - freshness.MAX_AGE_SECONDS - 1
        )
        result = enabled(downstream, stale)(ready_gate())
        self.assertIn("USAGE_SNAPSHOT_STALE", result.reason_codes)
        self.assertIn("USAGE_CHECKPOINT_REQUIRED", result.reason_codes)
        downstream.assert_not_called()

    def test_future_snapshot_blocks_without_downstream(self):
        downstream = mock.Mock(return_value=action())
        result = enabled(
            downstream, snapshot(observed_at_epoch_s=NOW + 1)
        )(ready_gate())
        self.assertIn("USAGE_SNAPSHOT_FROM_FUTURE", result.reason_codes)
        downstream.assert_not_called()

    def test_fresh_unknown_capacity_is_blocked_by_existing_permit(self):
        downstream = mock.Mock(return_value=action())
        result = enabled(
            downstream, snapshot(five_hour_remaining_pct=None)
        )(ready_gate())
        self.assertIn("USAGE_REMAINING_UNKNOWN", result.reason_codes)
        self.assertIn("USAGE_CHECKPOINT_REQUIRED", result.reason_codes)
        downstream.assert_not_called()

    def test_fresh_large_task_buffer_remains_blocked(self):
        downstream = mock.Mock(return_value=action())
        result = enabled(downstream, snapshot(
            five_hour_remaining_pct=15, task_size="LARGE"
        ))(ready_gate())
        self.assertIn("FIVE_HOUR_LARGE_TASK_STOP", result.reason_codes)
        self.assertNotIn("USAGE_CHECKPOINT_REQUIRED", result.reason_codes)
        downstream.assert_not_called()

    def test_production_disabled_adapter_has_no_start_path(self):
        result = adapter.FreshUsageProtectedStartAdapter.disabled()(
            ready_gate()
        )
        self.assertEqual(result.status, coordinator.ACTION_FAILED)
        self.assertEqual(
            result.reason_codes, ("FRESH_USAGE_START_ADAPTER_DISABLED",)
        )

    def test_downstream_uncertain_is_preserved_without_retry(self):
        downstream = mock.Mock(return_value=action(
            coordinator.ACTION_UNCERTAIN, ("START_OUTCOME_UNKNOWN",)
        ))
        result = enabled(downstream)(ready_gate())
        self.assertEqual(result.status, coordinator.ACTION_UNCERTAIN)
        self.assertEqual(result.reason_codes, ("START_OUTCOME_UNKNOWN",))
        downstream.assert_called_once()

    def test_downstream_exception_fails_without_retry(self):
        downstream = mock.Mock(side_effect=RuntimeError)
        result = enabled(downstream)(ready_gate())
        self.assertEqual(result.reason_codes, ("DOWNSTREAM_START_EXCEPTION",))
        downstream.assert_called_once()

    def test_composition_reads_no_clock_or_io(self):
        with (mock.patch("time.time", side_effect=AssertionError),
              mock.patch("builtins.open", side_effect=AssertionError),
              mock.patch("pathlib.Path.write_text", side_effect=AssertionError)):
            result = enabled(mock.Mock(return_value=action()))(ready_gate())
        self.assertEqual(result.status, coordinator.ACTION_SUCCEEDED)


if __name__ == "__main__":
    unittest.main()
