from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_expansion_collector_plan as subject  # noqa: E402


def evidence(**changes):
    values = {
        "target_count": 300,
        "fresh_eligible_count": 108,
        "isolated_database_verified": False,
        "request_budget_confirmed": False,
        "rate_limit_safety_confirmed": False,
        "overlap_and_uniqueness_validation_ready": False,
        "backup_and_restore_verified": False,
        "production_schedule_unchanged": True,
    }
    values.update(changes)
    return subject.ExpansionCollectorEvidence(**values)


class ExpansionCollectorPlanTests(unittest.TestCase):
    def test_current_plan_is_blocked_and_non_executing(self):
        result = subject.assess(subject.current_evidence())
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertEqual(result.current_policy_item_count, 100)
        self.assertEqual(result.proposed_request_count, 6)
        self.assertEqual(result.fresh_eligible_gap, 192)
        self.assertFalse(result.api_request_allowed)
        self.assertFalse(result.database_write_allowed)
        self.assertFalse(result.production_schedule_change_allowed)
        self.assertFalse(result.publication_allowed)
        self.assertIn("CURRENT_REQUEST_BUDGET_EXCEEDED", result.reason_codes)
        self.assertNotIn("ISOLATED_DATABASE_UNVERIFIED", result.reason_codes)
        self.assertNotIn("BACKUP_RESTORE_UNVERIFIED", result.reason_codes)

    def test_request_math_and_spacing_are_bounded(self):
        result = subject.assess(subject.current_evidence())
        self.assertEqual(result.proposed_hits, 50)
        self.assertEqual(result.minimum_request_spacing_seconds, 1.0)
        self.assertEqual(result.estimated_minimum_request_span_seconds, 5.0)

    def test_complete_evidence_still_requires_policy_budget_change(self):
        result = subject.assess(evidence(
            isolated_database_verified=True,
            request_budget_confirmed=True,
            rate_limit_safety_confirmed=True,
            overlap_and_uniqueness_validation_ready=True,
            backup_and_restore_verified=True,
        ))
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertEqual(result.reason_codes, ("CURRENT_REQUEST_BUDGET_EXCEEDED",))
        self.assertTrue(result.explicit_approval_required)
        self.assertFalse(result.api_request_allowed)

    def test_wrong_target_blocks(self):
        result = subject.assess(evidence(target_count=500))
        self.assertIn("TARGET_STAGE_INVALID", result.reason_codes)

    def test_schedule_mutation_blocks(self):
        result = subject.assess(evidence(production_schedule_unchanged=False))
        self.assertIn("PRODUCTION_SCHEDULE_CHANGE_DETECTED", result.reason_codes)

    def test_invalid_input_fails_closed(self):
        self.assertEqual(subject.assess({}).status, subject.FAIL_CLOSED)
        self.assertEqual(
            subject.assess(evidence(fresh_eligible_count=True)).status,
            subject.FAIL_CLOSED,
        )


if __name__ == "__main__":
    unittest.main()
