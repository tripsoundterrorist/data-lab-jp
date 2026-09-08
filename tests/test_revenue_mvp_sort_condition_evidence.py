from pathlib import Path
import json
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_sort_condition_evidence as evidence  # noqa: E402


class RevenueMvpSortConditionEvidenceTests(unittest.TestCase):
    def test_six_fail_closed_conditions_are_evidence_ready(self):
        result = evidence.assess_sort_condition_evidence()
        self.assertEqual(result.status, evidence.EVIDENCE_READY)
        self.assertTrue(result.implementation_evidence_candidate)
        self.assertEqual((result.checks_passed, result.checks_required), (6, 6))
        self.assertFalse(result.official_semantics_resolved)
        self.assertFalse(result.publication_gate_unlock_allowed)

    def test_policy_failure_blocks_without_details(self):
        with mock.patch.object(
            evidence.collection_policy,
            "evaluate_collection_policy",
            side_effect=RuntimeError("credential detail"),
        ):
            result = evidence.assess_sort_condition_evidence()
        serialized = json.dumps(result.to_dict())
        self.assertEqual(result.status, evidence.BLOCKED)
        self.assertFalse(result.implementation_evidence_candidate)
        self.assertNotIn("credential", serialized)
        self.assertNotIn("detail", serialized)

    def test_source_has_no_mutation_or_external_io(self):
        source = Path(evidence.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "sqlite3", "urllib", "requests", "subprocess", "INSERT",
            "UPDATE", "DELETE", "fetch(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
