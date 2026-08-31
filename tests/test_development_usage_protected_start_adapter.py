from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import development_gate_coordinator as coordinator  # noqa: E402
import development_gate_evidence as gate_core  # noqa: E402
import development_usage_protected_start_adapter as adapter  # noqa: E402
import development_usage_protection_permit as usage_core  # noqa: E402


CHECKPOINT = "a" * 64
SHA = "b" * 40


def ready_gate():
    return gate_core.DevelopmentGateEvidence(
        "current-gate", "next-gate", checkpoint_status="SAVED",
        checkpoint_ref=CHECKPOINT, test_tier="REGRESSION",
        test_status="PASSED", commit_sha=SHA, pushed_sha=SHA,
        ci_status="SUCCESS", ci_head_sha=SHA, ci_run_id=44,
        approval_status="APPROVED",
    )


def usage(five=100, weekly=74, size="SMALL", reserve=True):
    return usage_core.UsageProtectionEvidence(
        five, weekly, size, reserve
    )


def action(status=coordinator.ACTION_SUCCEEDED, evidence=None,
           action_name="START_NEXT_GATE", reasons=("START_CONFIRMED",)):
    return coordinator.DevelopmentGateActionResult(
        coordinator.ACTION_RESULT_VERSION, action_name, status, evidence,
        reasons,
    )


class DevelopmentUsageProtectedStartAdapterTests(unittest.TestCase):
    def test_permitted_evidence_invokes_downstream_once_through_coordinator(self):
        downstream = mock.Mock(return_value=action())
        protected = adapter.UsageProtectedStartAdapter._for_test(
            downstream, usage()
        )
        result = coordinator.DevelopmentGateCoordinator._for_test({
            "START_NEXT_GATE": protected,
        }).coordinate(ready_gate())
        self.assertEqual(result.status, "NEXT_GATE_STARTED")
        downstream.assert_called_once_with(ready_gate())

    def test_unknown_usage_blocks_without_downstream_and_requires_checkpoint(self):
        downstream = mock.Mock(return_value=action())
        protected = adapter.UsageProtectedStartAdapter._for_test(
            downstream, usage(five=None)
        )
        result = protected(ready_gate())
        self.assertEqual(result.status, coordinator.ACTION_FAILED)
        self.assertIn("USAGE_CHECKPOINT_REQUIRED", result.reason_codes)
        self.assertIn("USAGE_REMAINING_UNKNOWN", result.reason_codes)
        downstream.assert_not_called()

    def test_large_task_buffer_blocks_without_checkpoint_reason(self):
        downstream = mock.Mock(return_value=action())
        protected = adapter.UsageProtectedStartAdapter._for_test(
            downstream, usage(five=15, size="LARGE")
        )
        result = protected(ready_gate())
        self.assertIn("FIVE_HOUR_LARGE_TASK_STOP", result.reason_codes)
        self.assertNotIn("USAGE_CHECKPOINT_REQUIRED", result.reason_codes)
        downstream.assert_not_called()

    def test_operational_reserve_block_never_reaches_downstream(self):
        downstream = mock.Mock(return_value=action())
        result = adapter.UsageProtectedStartAdapter._for_test(
            downstream, usage(reserve=False)
        )(ready_gate())
        self.assertIn(
            "OPERATIONAL_RESERVE_NOT_PROTECTED", result.reason_codes
        )
        downstream.assert_not_called()

    def test_production_disabled_adapter_never_invokes_downstream(self):
        result = adapter.UsageProtectedStartAdapter.disabled()(ready_gate())
        self.assertEqual(result.status, coordinator.ACTION_FAILED)
        self.assertEqual(
            result.reason_codes,
            ("USAGE_PROTECTED_START_ADAPTER_DISABLED",),
        )

    def test_downstream_exception_fails_without_retry(self):
        downstream = mock.Mock(side_effect=RuntimeError)
        result = adapter.UsageProtectedStartAdapter._for_test(
            downstream, usage()
        )(ready_gate())
        self.assertEqual(result.reason_codes, ("DOWNSTREAM_START_EXCEPTION",))
        downstream.assert_called_once()

    def test_downstream_uncertain_is_preserved_without_retry(self):
        downstream = mock.Mock(return_value=action(
            coordinator.ACTION_UNCERTAIN, reasons=("START_OUTCOME_UNKNOWN",)
        ))
        result = adapter.UsageProtectedStartAdapter._for_test(
            downstream, usage()
        )(ready_gate())
        self.assertEqual(result.status, coordinator.ACTION_UNCERTAIN)
        self.assertEqual(result.reason_codes, ("START_OUTCOME_UNKNOWN",))
        downstream.assert_called_once()

    def test_downstream_failure_is_preserved_without_retry(self):
        downstream = mock.Mock(return_value=action(
            coordinator.ACTION_FAILED, reasons=("START_REJECTED",)
        ))
        result = adapter.UsageProtectedStartAdapter._for_test(
            downstream, usage()
        )(ready_gate())
        self.assertEqual(result.status, coordinator.ACTION_FAILED)
        self.assertEqual(result.reason_codes, ("START_REJECTED",))
        downstream.assert_called_once()

    def test_malformed_downstream_results_fail_closed(self):
        cases = (
            None,
            action(action_name="WAIT_FOR_CI"),
            action(evidence=ready_gate()),
            coordinator.DevelopmentGateActionResult(
                "9.9", "START_NEXT_GATE", coordinator.ACTION_SUCCEEDED,
                None, (),
            ),
        )
        for returned in cases:
            with self.subTest(returned=returned):
                result = adapter.UsageProtectedStartAdapter._for_test(
                    mock.Mock(return_value=returned), usage()
                )(ready_gate())
                self.assertEqual(
                    result.reason_codes,
                    ("DOWNSTREAM_START_RESULT_INVALID",),
                )

    def test_guard_performs_no_io(self):
        with (mock.patch("builtins.open", side_effect=AssertionError),
              mock.patch("pathlib.Path.write_text", side_effect=AssertionError)):
            result = adapter.UsageProtectedStartAdapter._for_test(
                mock.Mock(return_value=action()), usage()
            )(ready_gate())
        self.assertEqual(result.status, coordinator.ACTION_SUCCEEDED)


if __name__ == "__main__":
    unittest.main()
