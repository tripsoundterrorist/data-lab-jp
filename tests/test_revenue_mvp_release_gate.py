from pathlib import Path
from types import SimpleNamespace
from contextlib import redirect_stdout
from io import StringIO
import json
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_release_gate as gate  # noqa: E402


class RevenueMvpReleaseGateTests(unittest.TestCase):
    def setUp(self):
        self.production_smoke = mock.patch.object(
            gate.revenue_mvp_production_smoke_gate,
            "run_gate",
            return_value=SimpleNamespace(
                status="PRODUCTION_SHELL_VALIDATED",
                checked_url_count=14,
                failed_url_count=0,
                failed_check_group_count=0,
                reason_codes=("PRODUCTION_HTTP_VALIDATED", "ITEM_INDEXING_BLOCKED"),
            ),
        )
        self.production_smoke.start()
        self.addCleanup(self.production_smoke.stop)

    def test_current_state_reports_exact_release_blockers(self):
        result = gate.run_gate()
        self.assertEqual(result.status, gate.BLOCKED)
        self.assertFalse(result.production_release_allowed)
        self.assertFalse(result.affiliate_integration_allowed)
        self.assertEqual(result.shell_status, "SHELL_VALIDATED")
        self.assertEqual(result.production_smoke_status, "PRODUCTION_SHELL_VALIDATED")
        self.assertEqual(result.production_smoke_checked_url_count, 14)
        self.assertEqual(result.production_smoke_failed_url_count, 0)
        self.assertEqual(result.production_smoke_failed_check_group_count, 0)
        self.assertEqual(result.search_console_status, "PUBLIC_SHELL_READY")
        self.assertTrue(result.public_shell_indexing_allowed)
        self.assertEqual(result.official_answer_status, "FAIL_CLOSED")
        self.assertFalse(result.core_official_answer_candidate)
        self.assertFalse(result.sns_official_answer_candidate)
        self.assertFalse(result.official_answer_gate_unlock_allowed)
        self.assertEqual(result.x_funnel_status, "PREVIEW_ONLY")
        self.assertFalse(result.x_manual_post_candidate)
        self.assertFalse(result.x_automatic_post_allowed)
        self.assertEqual(result.public_data_state, "UNPUBLISHED")
        self.assertIn("REVENUE_MVP_RELEASE_BLOCKED", result.reason_codes)
        self.assertIn("WAIT_FOR_DMM_LIFECYCLE_RESPONSE", result.next_actions)
        self.assertIn("WAIT_FOR_DMM_SORT_SEMANTICS_RESPONSE", result.next_actions)
        self.assertNotIn("SUBMIT_SITEMAP_IN_SEARCH_CONSOLE", result.next_actions)
        self.assertNotIn("REQUEST_HOME_URL_INSPECTION", result.next_actions)
        self.assertIn("MONITOR_SITEMAP_PROCESSING", result.next_actions)
        self.assertIn("MONITOR_HOME_INDEX_STATUS", result.next_actions)
        self.assertIn("DO_NOT_REQUEST_ITEM_INDEXING", result.next_actions)
        self.assertIn("WAIT_FOR_DMM_FANZA_OFFICIAL_RESPONSE", result.next_actions)
        self.assertIn("WAIT_FOR_DMM_FANZA_SNS_RESPONSE", result.next_actions)

    def test_search_console_failure_blocks_otherwise_ready_release(self):
        deployment = SimpleNamespace(
            status="READY", public_data_state="APPROVED_CANDIDATE",
            public_data_deployment_allowed=True, reason_codes=(),
        )
        publication = SimpleNamespace(
            overall_readiness="READY", overall_eligible=True,
            reason_codes=(), next_actions=(),
        )
        search_console = SimpleNamespace(
            status="FAIL_CLOSED", public_shell_indexing_allowed=False,
            reason_codes=("CANONICAL_MISMATCH",), next_actions=("FIX_SEO_GATE_FAILURE",),
        )
        with (
            mock.patch.object(gate.revenue_mvp_deployment_preflight, "run_preflight", return_value=deployment),
            mock.patch.object(gate.publication_readiness, "build_report", return_value=publication),
            mock.patch.object(gate.revenue_mvp_search_console_gate, "run_gate", return_value=search_console),
        ):
            result = gate.run_gate()
        self.assertEqual(result.status, gate.BLOCKED)
        self.assertFalse(result.affiliate_integration_allowed)
        self.assertIn("CANONICAL_MISMATCH", result.reason_codes)

    def test_production_smoke_failure_blocks_otherwise_ready_release(self):
        deployment = SimpleNamespace(
            status="READY", public_data_state="APPROVED_CANDIDATE",
            public_data_deployment_allowed=True, reason_codes=(),
        )
        publication = SimpleNamespace(
            overall_readiness="READY", overall_eligible=True,
            reason_codes=(), next_actions=(),
        )
        search_console = SimpleNamespace(
            status="PUBLIC_SHELL_READY", public_shell_indexing_allowed=True,
            reason_codes=(), next_actions=(),
        )
        production_smoke = SimpleNamespace(
            status="FAIL_CLOSED", checked_url_count=13,
            failed_url_count=1, failed_check_group_count=1,
            reason_codes=("PUBLIC_INFORMATION_FETCH_FAILED",),
        )
        with (
            mock.patch.object(gate.revenue_mvp_deployment_preflight, "run_preflight", return_value=deployment),
            mock.patch.object(gate.publication_readiness, "build_report", return_value=publication),
            mock.patch.object(gate.revenue_mvp_search_console_gate, "run_gate", return_value=search_console),
            mock.patch.object(gate.revenue_mvp_production_smoke_gate, "run_gate", return_value=production_smoke),
        ):
            result = gate.run_gate()
        self.assertEqual(result.status, gate.BLOCKED)
        self.assertFalse(result.affiliate_integration_allowed)
        self.assertEqual(result.production_smoke_failed_url_count, 1)
        self.assertEqual(result.production_smoke_failed_check_group_count, 1)
        self.assertIn("PUBLIC_INFORMATION_FETCH_FAILED", result.reason_codes)

    def test_core_answer_candidate_is_required_but_sns_is_not(self):
        deployment = SimpleNamespace(
            status="READY", public_data_state="APPROVED_CANDIDATE",
            public_data_deployment_allowed=True, reason_codes=(),
        )
        publication = SimpleNamespace(
            overall_readiness="READY", overall_eligible=True,
            reason_codes=(), next_actions=(),
        )
        search_console = SimpleNamespace(
            status="PUBLIC_SHELL_READY", public_shell_indexing_allowed=True,
            reason_codes=(), next_actions=(),
        )
        official_answers = SimpleNamespace(
            status="REVIEW_CANDIDATE", core_publication_candidate=True,
            sns_operation_candidate=False, gate_unlock_allowed=False,
            reason_codes=("UNRESOLVED_OR_UNVERIFIED_TOPICS",),
        )
        with (
            mock.patch.object(gate.revenue_mvp_deployment_preflight, "run_preflight", return_value=deployment),
            mock.patch.object(gate.publication_readiness, "build_report", return_value=publication),
            mock.patch.object(gate.revenue_mvp_search_console_gate, "run_gate", return_value=search_console),
            mock.patch.object(gate.revenue_mvp_official_answer_matrix, "assess_answer_matrix", return_value=official_answers),
        ):
            result = gate.run_gate()
        self.assertEqual(result.status, gate.READY_FOR_RELEASE_APPROVAL)
        self.assertTrue(result.affiliate_integration_allowed)
        self.assertFalse(result.production_release_allowed)
        self.assertFalse(result.sns_official_answer_candidate)
        self.assertFalse(result.official_answer_gate_unlock_allowed)
        self.assertEqual(result.x_funnel_status, "PREVIEW_ONLY")
        self.assertIn("WAIT_FOR_DMM_FANZA_SNS_RESPONSE", result.next_actions)

    def test_deployment_ready_cannot_override_official_blockers(self):
        deployment = SimpleNamespace(
            status="READY", public_data_state="APPROVED_CANDIDATE",
            public_data_deployment_allowed=True, reason_codes=(),
        )
        with mock.patch.object(
            gate.revenue_mvp_deployment_preflight, "run_preflight",
            return_value=deployment,
        ):
            result = gate.run_gate()
        self.assertEqual(result.status, gate.BLOCKED)
        self.assertFalse(result.affiliate_integration_allowed)

    def test_internal_failure_is_bounded_and_fail_closed(self):
        with mock.patch.object(
            gate.revenue_mvp_deployment_preflight, "run_preflight",
            side_effect=RuntimeError("secret URL"),
        ):
            result = gate.run_gate()
        self.assertEqual(result.status, gate.FAIL_CLOSED)
        self.assertFalse(result.production_release_allowed)
        self.assertEqual(result.search_console_status, "UNKNOWN")
        self.assertEqual(result.production_smoke_status, "UNKNOWN")
        self.assertEqual(result.production_smoke_checked_url_count, 0)
        self.assertEqual(result.official_answer_status, "UNKNOWN")
        self.assertEqual(result.x_funnel_status, "UNKNOWN")
        self.assertNotIn("secret", json.dumps(result.to_dict()))

    def test_cli_is_read_only_and_machine_readable(self):
        output = StringIO()
        with redirect_stdout(output):
            return_code = gate.main([])
        self.assertEqual(return_code, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], gate.BLOCKED)
        self.assertFalse(result["production_release_allowed"])
        self.assertEqual(result["x_funnel_status"], "PREVIEW_ONLY")
        self.assertEqual(result["production_smoke_status"], "PRODUCTION_SHELL_VALIDATED")
        self.assertGreaterEqual(result["production_smoke_checked_url_count"], 0)
        self.assertGreaterEqual(result["production_smoke_failed_url_count"], 0)
        self.assertGreaterEqual(result["production_smoke_failed_check_group_count"], 0)


if __name__ == "__main__":
    unittest.main()
