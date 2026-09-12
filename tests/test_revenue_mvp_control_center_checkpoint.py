from dataclasses import replace
from pathlib import Path
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_control_center_checkpoint as checkpoint  # noqa: E402


class RevenueMvpControlCenterCheckpointTests(unittest.TestCase):
    def inputs(self):
        followup = checkpoint.revenue_mvp_official_followup_status.current_status()
        artifact = checkpoint.revenue_mvp_publication_artifact_evidence.assess_evidence()
        d1 = checkpoint.affiliate_d1_production_state.assess(
            checkpoint.affiliate_d1_production_state.current_evidence()
        )
        runbook = checkpoint.revenue_mvp_activation_runbook.current_runbook()
        launch = checkpoint.revenue_mvp_launch_rehearsal.run_rehearsal()
        response = checkpoint.revenue_mvp_official_response_rehearsal.run_rehearsal()
        return followup, artifact, d1, runbook, launch, response

    def test_current_checkpoint_is_consistent_and_closed(self):
        result = checkpoint.build_checkpoint(*self.inputs())
        self.assertEqual(result.status, checkpoint.READY_WAITING)
        self.assertEqual(result.revenue_mvp_priority, "P0")
        self.assertEqual(result.public_artifact_item_count, 861)
        self.assertEqual(result.d1_row_count, 861)
        self.assertEqual(result.d1_enabled_row_count, 0)
        self.assertTrue(result.official_response_pending)
        self.assertTrue(result.offline_launch_rehearsal_passed)
        self.assertTrue(result.official_response_rehearsal_passed)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_activation_allowed)
        self.assertFalse(result.paid_plan_change_allowed)
        self.assertEqual(result.next_action, checkpoint.NEXT_ACTION)

    def test_changed_or_unsafe_fact_fails_closed(self):
        cases = (
            (0, "response_received", True),
            (1, "publication_allowed", True),
            (2, "all_rows_disabled", False),
            (3, "production_activation_allowed", True),
            (4, "deploy_allowed", True),
            (5, "gate_unlock_allowed", True),
        )
        for index, field, value in cases:
            values = list(self.inputs())
            values[index] = replace(values[index], **{field: value})
            with self.subTest(field=field):
                result = checkpoint.build_checkpoint(*values)
                self.assertEqual(result.status, checkpoint.FAIL_CLOSED)
                self.assertFalse(result.publication_allowed)
                self.assertFalse(result.production_activation_allowed)
                self.assertFalse(result.paid_plan_change_allowed)

    def test_count_drift_fails_closed(self):
        values = list(self.inputs())
        values[1] = replace(values[1], item_count=860)
        result = checkpoint.build_checkpoint(*values)
        self.assertEqual(result.status, checkpoint.FAIL_CLOSED)
        self.assertIsNone(result.public_artifact_item_count)

    def test_safe_output_contains_no_sensitive_or_item_level_data(self):
        rendered = json.dumps(
            checkpoint.build_checkpoint(*self.inputs()).to_dict()
        ).casefold()
        for forbidden in (
            "content_id", "public_id", "https://", "api_id", "affiliate_id",
            "raw_email", "sender", "account_id", "database_id",
        ):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
