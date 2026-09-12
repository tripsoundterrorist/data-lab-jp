from pathlib import Path
from types import SimpleNamespace
import copy
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_control_center_checkpoint as checkpoint  # noqa: E402


class RevenueMvpControlCenterCheckpointTests(unittest.TestCase):
    def inputs(self):
        followup = SimpleNamespace(
            version="0.1", status="SUBMITTED_AWAITING_RESPONSE",
            response_received=False, gate_unlock_allowed=False,
        )
        artifact = SimpleNamespace(
            version="0.1", status="ARTIFACT_VALIDATION_EVIDENCE_READY",
            source_db_matches=True, artifact_validation_passed=True,
            publication_allowed=False, production_write_performed=False,
            gate_unlock_allowed=False, item_count=861,
        )
        d1 = SimpleNamespace(
            version="0.1", status="READY_FOR_INERT_RUNTIME_REVIEW",
            lookup_ready=True, all_rows_disabled=True, all_rows_pending=True,
            runtime_eligibility_empty=True, cloudflare_write_allowed=False,
            deployment_allowed=False, paid_plan_change_allowed=False,
            row_count=861,
        )
        runbook = SimpleNamespace(
            version="0.1", status="WAITING_FOR_OFFICIAL_RESPONSE",
            production_activation_allowed=False, paid_plan_change_allowed=False,
            next_step="INTAKE_AND_CLASSIFY_DMM_RESPONSE",
            public_artifact_item_count=861, d1_row_count=861,
            d1_runtime_eligible_count=0,
        )
        launch = SimpleNamespace(
            version="0.1", status="OFFLINE_LAUNCH_REHEARSAL_PASS",
            production_write_performed=False, network_request_performed=False,
            deploy_allowed=False, paid_plan_change_allowed=False,
        )
        response = SimpleNamespace(
            version="0.1", status="OFFICIAL_RESPONSE_REHEARSAL_PASS",
            gate_unlock_allowed=False, production_activation_allowed=False,
        )
        response_path = SimpleNamespace(
            version="0.1", status="OFFICIAL_RESPONSE_PATH_REHEARSAL_PASS",
            checks_passed=6, checks_required=6,
            no_mutation_boundary_verified=True,
            network_request_performed=False, production_write_performed=False,
            gate_mutation_allowed=False, production_activation_allowed=False,
        )
        return followup, artifact, d1, runbook, launch, response, response_path

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
        self.assertTrue(result.official_response_path_rehearsal_passed)
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
            (6, "no_mutation_boundary_verified", False),
            (6, "production_activation_allowed", True),
        )
        for index, field, value in cases:
            values = list(self.inputs())
            values[index] = copy.copy(values[index])
            setattr(values[index], field, value)
            with self.subTest(field=field):
                result = checkpoint.build_checkpoint(*values)
                self.assertEqual(result.status, checkpoint.FAIL_CLOSED)
                self.assertFalse(result.publication_allowed)
                self.assertFalse(result.production_activation_allowed)
                self.assertFalse(result.paid_plan_change_allowed)

    def test_count_drift_fails_closed(self):
        values = list(self.inputs())
        values[1] = copy.copy(values[1])
        values[1].item_count = 860
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
