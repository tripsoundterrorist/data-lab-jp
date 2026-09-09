from pathlib import Path
from types import SimpleNamespace
import json
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_next_gate_plan as plan  # noqa: E402


class RevenueMvpNextGatePlanTests(unittest.TestCase):
    @staticmethod
    def lifecycle_evidence(**overrides):
        values = {
            "version": plan.revenue_mvp_lifecycle_condition_evidence.VERSION,
            "status": plan.revenue_mvp_lifecycle_condition_evidence.EVIDENCE_READY,
            "implementation_evidence_candidate": True,
            "official_semantics_resolved": False,
            "publication_gate_unlock_allowed": False,
            "checks_passed": 5,
            "checks_required": 5,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    @staticmethod
    def sort_evidence(**overrides):
        values = {
            "version": plan.revenue_mvp_sort_condition_evidence.VERSION,
            "status": plan.revenue_mvp_sort_condition_evidence.EVIDENCE_READY,
            "implementation_evidence_candidate": True,
            "official_semantics_resolved": False,
            "publication_gate_unlock_allowed": False,
            "checks_passed": 6,
            "checks_required": 6,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    @staticmethod
    def temporal_continuation(**overrides):
        values = {
            "version": plan.revenue_mvp_temporal_continuation_assessment.VERSION,
            "status": plan.revenue_mvp_temporal_continuation_assessment.LONG_GAP_BLOCKED,
            "api_request_authorized": False,
            "state_write_authorized": False,
            "fresh_baseline_policy_required": True,
            "populations_found": 4,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    @staticmethod
    def temporal_series_evidence(**overrides):
        values = {
            "version": plan.revenue_mvp_temporal_series_candidate_evidence.VERSION,
            "status": plan.revenue_mvp_temporal_series_candidate_evidence.EVIDENCE_READY,
            "implementation_evidence_candidate": True,
            "isolated_integration_adapter_verified": True,
            "active_pipeline_connected": False,
            "api_request_authorized": False,
            "state_write_authorized": False,
            "baseline_activation_authorized": False,
            "checks_passed": 8,
            "checks_required": 8,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def build_plan(
        self,
        release,
        lifecycle_evidence=None,
        sort_evidence=None,
        temporal_continuation=None,
        temporal_series_evidence=None,
    ):
        return plan.build_plan(
            release,
            lifecycle_evidence or self.lifecycle_evidence(),
            sort_evidence or self.sort_evidence(),
            temporal_continuation or self.temporal_continuation(),
            temporal_series_evidence or self.temporal_series_evidence(),
        )

    def test_actions_are_split_without_authorization(self):
        release = SimpleNamespace(
            status="BLOCKED",
            next_actions=(
                "VERIFY_PRODUCTION_DOMAIN_APPROVAL",
                "IMPLEMENT_DMM_LIFECYCLE_CONDITIONS",
                "CONFIGURE_REQUIRED_SECRET_BINDINGS",
                "IMPLEMENT_DMM_SORT_SEMANTICS_CONDITIONS",
                "CONTINUE_TEMPORAL_OBSERVATION",
            ),
        )
        result = self.build_plan(
            release, self.lifecycle_evidence(), self.sort_evidence()
        )
        self.assertEqual(result.status, plan.BLOCKED)
        self.assertFalse(result.production_release_allowed)
        self.assertEqual(
            result.safe_local_actions,
            (
                plan.DERIVED_SAFE_ACTION,
            ),
        )
        self.assertEqual(
            result.external_boundary_actions,
            (
                "OBTAIN_SEPARATE_DMM_LIFECYCLE_SEMANTICS_CONFIRMATION",
                "OBTAIN_SEPARATE_DMM_SORT_SEMANTICS_CONFIRMATION",
                "VERIFY_PRODUCTION_DOMAIN_APPROVAL",
                "CONFIGURE_REQUIRED_SECRET_BINDINGS",
            ),
        )
        self.assertEqual(
            result.next_safe_local_action,
            plan.DERIVED_SAFE_ACTION,
        )

    def test_incomplete_evidence_retains_local_lifecycle_action(self):
        release = SimpleNamespace(
            status="BLOCKED",
            next_actions=("IMPLEMENT_DMM_LIFECYCLE_CONDITIONS",),
        )
        result = self.build_plan(
            release,
            self.lifecycle_evidence(
                status=plan.revenue_mvp_lifecycle_condition_evidence.BLOCKED,
                implementation_evidence_candidate=False,
                checks_passed=4,
            ),
            self.sort_evidence(),
        )
        self.assertEqual(
            result.safe_local_actions,
            ("IMPLEMENT_DMM_LIFECYCLE_CONDITIONS",),
        )
        self.assertEqual(
            result.external_boundary_actions,
            ("OBTAIN_SEPARATE_DMM_SORT_SEMANTICS_CONFIRMATION",),
        )

    def test_unknown_duplicate_or_non_tuple_actions_fail_closed(self):
        for actions in (
            ("UNKNOWN_ACTION",),
            ("MONITOR_INDEX_COVERAGE", "MONITOR_INDEX_COVERAGE"),
            ["MONITOR_INDEX_COVERAGE"],
        ):
            with self.subTest(actions=actions):
                result = self.build_plan(
                    SimpleNamespace(status="BLOCKED", next_actions=actions),
                    self.lifecycle_evidence(),
                    self.sort_evidence(),
                )
                self.assertEqual(result.status, plan.FAIL_CLOSED)
                self.assertFalse(result.production_release_allowed)

    def test_input_and_internal_details_are_not_returned(self):
        result = self.build_plan(
            SimpleNamespace(
                status="BLOCKED",
                next_actions=("secret URL https://invalid",),
            ),
            self.lifecycle_evidence(),
            self.sort_evidence(),
        )
        serialized = json.dumps(result.to_dict())
        self.assertEqual(result.status, plan.FAIL_CLOSED)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("https://", serialized)

    def test_malformed_lifecycle_evidence_fails_closed(self):
        release = SimpleNamespace(status="BLOCKED", next_actions=())
        result = self.build_plan(
            release,
            self.lifecycle_evidence(official_semantics_resolved=True),
            self.sort_evidence(),
        )
        self.assertEqual(result.status, plan.FAIL_CLOSED)
        self.assertFalse(result.production_release_allowed)

    def test_incomplete_sort_evidence_retains_local_sort_action(self):
        release = SimpleNamespace(
            status="BLOCKED",
            next_actions=("IMPLEMENT_DMM_SORT_SEMANTICS_CONDITIONS",),
        )
        result = self.build_plan(
            release,
            self.lifecycle_evidence(),
            self.sort_evidence(
                status=plan.revenue_mvp_sort_condition_evidence.BLOCKED,
                implementation_evidence_candidate=False,
                checks_passed=5,
            ),
        )
        self.assertEqual(
            result.safe_local_actions,
            ("IMPLEMENT_DMM_SORT_SEMANTICS_CONDITIONS",),
        )
        self.assertNotIn(
            "OBTAIN_SEPARATE_DMM_SORT_SEMANTICS_CONFIRMATION",
            result.external_boundary_actions,
        )

    def test_malformed_sort_evidence_fails_closed(self):
        release = SimpleNamespace(status="BLOCKED", next_actions=())
        result = self.build_plan(
            release,
            self.lifecycle_evidence(),
            self.sort_evidence(publication_gate_unlock_allowed=True),
        )
        self.assertEqual(result.status, plan.FAIL_CLOSED)
        self.assertFalse(result.production_release_allowed)

    def test_non_long_gap_retains_temporal_observation_action(self):
        release = SimpleNamespace(
            status="BLOCKED",
            next_actions=("CONTINUE_TEMPORAL_OBSERVATION",),
        )
        result = self.build_plan(
            release,
            temporal_continuation=self.temporal_continuation(
                status=plan.revenue_mvp_temporal_continuation_assessment.WAIT,
                fresh_baseline_policy_required=False,
            ),
        )
        self.assertEqual(
            result.safe_local_actions, ("CONTINUE_TEMPORAL_OBSERVATION",)
        )

    def test_permissive_temporal_input_fails_closed(self):
        release = SimpleNamespace(status="BLOCKED", next_actions=())
        result = self.build_plan(
            release,
            temporal_continuation=self.temporal_continuation(
                api_request_authorized=True
            ),
        )
        self.assertEqual(result.status, plan.FAIL_CLOSED)
        self.assertFalse(result.production_release_allowed)

    def test_unverified_integration_adapter_fails_closed(self):
        release = SimpleNamespace(status="BLOCKED", next_actions=())
        result = self.build_plan(
            release,
            temporal_series_evidence=self.temporal_series_evidence(
                isolated_integration_adapter_verified=False
            ),
        )
        self.assertEqual(result.status, plan.FAIL_CLOSED)

    def test_run_plan_uses_release_gate_read_only_summary(self):
        release = SimpleNamespace(
            status="BLOCKED",
            next_actions=("MONITOR_INDEX_COVERAGE",),
        )
        with mock.patch.object(
            plan.revenue_mvp_release_gate, "run_gate", return_value=release
        ) as gate, mock.patch.object(
            plan.revenue_mvp_lifecycle_condition_evidence,
            "assess_lifecycle_condition_evidence",
            return_value=self.lifecycle_evidence(),
        ) as lifecycle, mock.patch.object(
            plan.revenue_mvp_sort_condition_evidence,
            "assess_sort_condition_evidence",
            return_value=self.sort_evidence(),
        ) as sort, mock.patch.object(
            plan.revenue_mvp_temporal_continuation_assessment,
            "assess_temporal_continuation",
            return_value=self.temporal_continuation(),
        ) as temporal, mock.patch.object(
            plan.revenue_mvp_temporal_series_candidate_evidence,
            "assess_temporal_series_candidate_evidence",
            return_value=self.temporal_series_evidence(),
        ) as series:
            result = plan.run_plan()
        gate.assert_called_once_with()
        lifecycle.assert_called_once_with()
        sort.assert_called_once_with()
        temporal.assert_called_once()
        series.assert_called_once_with()
        self.assertEqual(result.safe_local_actions, ("MONITOR_INDEX_COVERAGE",))

    def test_release_gate_exception_fails_closed(self):
        with mock.patch.object(
            plan.revenue_mvp_release_gate,
            "run_gate",
            side_effect=RuntimeError("credential detail"),
        ):
            result = plan.run_plan()
        self.assertEqual(result.status, plan.FAIL_CLOSED)
        self.assertNotIn("credential", json.dumps(result.to_dict()))


if __name__ == "__main__":
    unittest.main()
