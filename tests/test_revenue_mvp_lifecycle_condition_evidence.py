from pathlib import Path
import json
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_lifecycle_condition_evidence as evidence  # noqa: E402


class RevenueMvpLifecycleConditionEvidenceTests(unittest.TestCase):
    def test_current_implementation_evidence_is_ready_but_cannot_unlock(self):
        result = evidence.assess_lifecycle_condition_evidence()
        self.assertEqual(result.status, evidence.EVIDENCE_READY)
        self.assertTrue(result.implementation_evidence_candidate)
        self.assertEqual(result.checks_passed, result.checks_required)
        self.assertFalse(result.official_semantics_resolved)
        self.assertFalse(result.publication_gate_unlock_allowed)
        self.assertIn("SEPARATE_OFFICIAL_SEMANTICS_REQUIRED", result.reason_codes)

    def test_dependency_regression_blocks_evidence(self):
        unsafe = mock.Mock(
            state=evidence.product_lifecycle.LifecycleState.CONFIRMED_AVAILABLE,
            lifecycle_eligible_for_publication=True,
        )
        with mock.patch.object(
            evidence.product_lifecycle,
            "evaluate_product_lifecycle",
            return_value=unsafe,
        ):
            result = evidence.assess_lifecycle_condition_evidence()
        self.assertEqual(result.status, evidence.BLOCKED)
        self.assertFalse(result.implementation_evidence_candidate)
        self.assertFalse(result.publication_gate_unlock_allowed)

    def test_internal_error_is_bounded(self):
        with mock.patch.object(
            evidence.product_lifecycle,
            "evaluate_product_lifecycle",
            side_effect=RuntimeError("secret lifecycle detail"),
        ):
            result = evidence.assess_lifecycle_condition_evidence()
        output = json.dumps(result.to_dict())
        self.assertEqual(result.status, evidence.BLOCKED)
        self.assertNotIn("secret", output)
        self.assertNotIn("detail", output)

    def test_source_has_no_mutation_or_external_io(self):
        source = Path(evidence.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "sqlite3", "urllib", "requests", "subprocess", "INSERT",
            "UPDATE", "DELETE", "fetch(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
