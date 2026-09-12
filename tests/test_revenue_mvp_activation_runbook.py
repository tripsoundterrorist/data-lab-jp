from pathlib import Path
from types import SimpleNamespace
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_activation_runbook as runbook  # noqa: E402


def inputs():
    followup = SimpleNamespace(
        version="0.1", status="SUBMITTED_AWAITING_RESPONSE",
        response_received=False, official_semantics_resolved=False,
        gate_unlock_allowed=False,
    )
    artifact = SimpleNamespace(
        version="0.1", status="ARTIFACT_VALIDATION_EVIDENCE_READY",
        source_db_matches=True, artifact_validation_passed=True,
        publication_allowed=False, production_write_performed=False,
        gate_unlock_allowed=False, item_count=861,
    )
    d1 = SimpleNamespace(
        status="READY_FOR_INERT_RUNTIME_REVIEW", lookup_ready=True,
        all_rows_disabled=True, all_rows_pending=True,
        runtime_eligibility_empty=True, cloudflare_write_allowed=False,
        deployment_allowed=False, paid_plan_change_allowed=False, row_count=861,
    )
    deployment = SimpleNamespace(
        status="READY_FOR_DEPLOYMENT_REVIEW", deployment_candidate=True,
        production_deployment_allowed=False,
    )
    return followup, artifact, d1, deployment


class RevenueMvpActivationRunbookTests(unittest.TestCase):
    def test_current_evidence_yields_exact_fail_closed_order(self):
        result = runbook.build_runbook(*inputs())
        self.assertEqual(result.status, runbook.WAITING)
        self.assertEqual(result.remaining_steps, runbook.ORDERED_STEPS)
        self.assertEqual(result.next_step, "INTAKE_AND_CLASSIFY_DMM_RESPONSE")
        self.assertEqual((result.d1_row_count, result.d1_runtime_eligible_count),
                         (861, 0))
        self.assertEqual(result.public_artifact_item_count, 861)
        self.assertFalse(result.production_activation_allowed)
        self.assertFalse(result.paid_plan_change_allowed)

    def test_each_unsafe_or_changed_fact_fails_closed(self):
        cases = (
            (0, "response_received", True),
            (1, "source_db_matches", False),
            (1, "publication_allowed", True),
            (2, "all_rows_disabled", False),
            (2, "cloudflare_write_allowed", True),
            (2, "paid_plan_change_allowed", True),
            (3, "production_deployment_allowed", True),
        )
        for index, key, value in cases:
            values = list(inputs())
            setattr(values[index], key, value)
            with self.subTest(key=key):
                result = runbook.build_runbook(*values)
                self.assertEqual(result.status, runbook.FAIL_CLOSED)
                self.assertFalse(result.production_activation_allowed)

    def test_safe_result_exposes_no_identifiers_urls_or_secrets(self):
        rendered = json.dumps(runbook.build_runbook(*inputs()).to_dict()).casefold()
        for forbidden in ("content_id", "public_id", "https://", "api_id", "affiliate_id"):
            self.assertNotIn(forbidden, rendered)

    def test_rollback_closes_runtime_before_data_or_artifact_changes(self):
        self.assertEqual(runbook.ROLLBACK_ORDER[0], "CLOSE_WORKER_RELEASE_FACTS")
        self.assertEqual(runbook.ROLLBACK_ORDER[-1], "RUN_BLOCKED_ROUTE_AND_SHELL_SMOKE")


if __name__ == "__main__":
    unittest.main()
