from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import notification_suppression_metrics as metrics  # noqa: E402
import unattended_runtime as runtime  # noqa: E402


def result(status, *, event_type="JOB_COMPLETED", selected=False,
           suppressed=False, attempted=False, succeeded=False,
           emergency=False, reasons=("FIXTURE_REASON",), **changes):
    values = {
        "runtime_version": runtime.RUNTIME_VERSION,
        "runtime_mode": "MOCK_RUNTIME",
        "runtime_status": status,
        "event_type": event_type,
        "notification_selected": selected,
        "notification_suppressed": suppressed,
        "delivery_attempted": attempted,
        "delivery_succeeded": succeeded,
        "approval_required": event_type == "JOB_WAITING_APPROVAL",
        "emergency_blocked": emergency,
        "reason_codes": reasons,
    }
    values.update(changes)
    return runtime.RuntimeResult(**values)


def delivered(*, reminder=False, **changes):
    reasons = ("INCIDENT_REMINDER_SELECTED", "NOTIFICATION_DELIVERED") \
        if reminder else ("NOTIFICATION_DELIVERED",)
    values = {
        "selected": True,
        "attempted": True,
        "succeeded": True,
        "reasons": reasons,
    }
    values.update(changes)
    return result("NOTIFICATION_DELIVERED", **values)


class NotificationSuppressionMetricsTests(unittest.TestCase):
    def test_empty_snapshot_is_safe_zero_metrics(self):
        actual = metrics.summarize([])
        self.assertEqual(actual.status, "METRICS_READY")
        self.assertEqual(
            (actual.sample_count, actual.delivered_count,
             actual.suppressed_count, actual.reminder_count,
             actual.failed_safe_count, actual.emergency_blocked_count),
            (0, 0, 0, 0, 0, 0),
        )

    def test_counts_delivery_suppression_reminder_and_boundaries(self):
        values = [
            delivered(), delivered(
                reminder=True, event_type="JOB_WAITING_APPROVAL"
            ),
            result(
                "NOTIFICATION_DUPLICATE_SUPPRESSED", selected=True,
                suppressed=True,
            ),
            result(
                "NOTIFICATION_SUPPRESSED", event_type="JOB_STARTED",
                suppressed=True,
            ),
            result("NOTIFICATION_FAILED_SAFE", selected=True),
            result(
                "EMERGENCY_SEND_BLOCKED", event_type="CRITICAL_STOP",
                selected=True, emergency=True,
            ),
        ]
        actual = metrics.summarize(values)
        self.assertEqual(actual.status, "METRICS_READY")
        self.assertEqual(
            (actual.sample_count, actual.delivered_count,
             actual.suppressed_count, actual.reminder_count,
             actual.failed_safe_count, actual.emergency_blocked_count),
            (6, 2, 2, 1, 1, 1),
        )

    def test_all_exact_suppression_shapes_are_recognized(self):
        values = [
            result("DUPLICATE_EVENT_SUPPRESSED", suppressed=True),
            result(
                "NOTIFICATION_SUPPRESSED", event_type="JOB_STARTED",
                suppressed=True,
            ),
            result(
                "NOTIFICATION_DUPLICATE_SUPPRESSED", selected=True,
                suppressed=True,
            ),
        ]
        actual = metrics.summarize(values)
        self.assertEqual(actual.suppressed_count, 3)

    def test_contradictory_flags_block_entire_snapshot(self):
        cases = (
            delivered(succeeded=False),
            result(
                "NOTIFICATION_DUPLICATE_SUPPRESSED", selected=False,
                suppressed=True,
            ),
            result(
                "NOTIFICATION_SUPPRESSED", selected=True, suppressed=True,
            ),
            result(
                "NOTIFICATION_FAILED_SAFE", suppressed=True,
            ),
            result(
                "EMERGENCY_SEND_BLOCKED", event_type="CRITICAL_STOP",
                selected=True, emergency=False,
            ),
        )
        for value in cases:
            with self.subTest(value=value):
                self.assertEqual(
                    metrics.summarize([value]).status, "METRICS_BLOCKED"
                )

    def test_reminder_only_allowed_on_successful_delivery(self):
        invalid = result(
            "NOTIFICATION_DUPLICATE_SUPPRESSED", selected=True,
            suppressed=True, reasons=("INCIDENT_REMINDER_SELECTED",),
        )
        self.assertEqual(metrics.summarize([invalid]).status, "METRICS_BLOCKED")

    def test_event_and_approval_combinations_are_exact(self):
        cases = (
            delivered(event_type="JOB_STARTED"),
            delivered(event_type="CRITICAL_STOP"),
            delivered(reminder=True, event_type="JOB_COMPLETED"),
            delivered(approval_required=True),
            result(
                "NOTIFICATION_SUPPRESSED", event_type="JOB_COMPLETED",
                suppressed=True,
            ),
            result(
                "NOTIFICATION_DUPLICATE_SUPPRESSED", event_type="JOB_STARTED",
                selected=True, suppressed=True,
            ),
            result("NOTIFICATION_FAILED_SAFE", event_type="JOB_STARTED"),
            result(
                "EMERGENCY_SEND_BLOCKED", event_type="JOB_FAILED_SAFE",
                selected=True, emergency=True,
            ),
        )
        for value in cases:
            with self.subTest(value=value):
                self.assertEqual(
                    metrics.summarize([value]).status, "METRICS_BLOCKED"
                )

    def test_only_mock_runtime_results_are_accepted(self):
        cases = (
            delivered(runtime_mode="LIVE_NOTIFICATION"),
            delivered(runtime_mode="DRY_RUN"),
            delivered(runtime_version="9.9"),
            delivered(event_type="UNKNOWN"),
            object(),
        )
        for value in cases:
            with self.subTest(value=value):
                self.assertEqual(
                    metrics.summarize([value]).status, "METRICS_BLOCKED"
                )

    def test_reason_codes_are_sanitized_but_not_emitted(self):
        invalid = delivered(reason_codes=("credential secret",))
        actual = metrics.summarize([invalid])
        self.assertEqual(actual.status, "METRICS_BLOCKED")
        self.assertNotIn("credential", repr(actual))

        safe = delivered(reason_codes=("FIXTURE_PRIVATE_REASON",))
        actual = metrics.summarize([safe])
        self.assertEqual(actual.status, "METRICS_READY")
        self.assertNotIn("FIXTURE_PRIVATE_REASON", repr(actual))

    def test_input_type_and_bound_are_exact(self):
        self.assertEqual(metrics.summarize(()).status, "METRICS_BLOCKED")
        self.assertEqual(
            metrics.summarize([delivered()] * (metrics.MAX_RESULTS + 1)).status,
            "METRICS_BLOCKED",
        )

    def test_inputs_are_not_mutated_and_module_has_no_io_surface(self):
        values = [
            delivered(),
            result(
                "NOTIFICATION_SUPPRESSED", event_type="JOB_STARTED",
                suppressed=True,
            ),
        ]
        before = list(values)
        metrics.summarize(values)
        self.assertEqual(values, before)
        self.assertFalse(hasattr(metrics, "send_notification"))
        self.assertFalse(hasattr(metrics, "write_metrics"))
        self.assertFalse(hasattr(metrics, "activate_live"))


if __name__ == "__main__":
    unittest.main()
