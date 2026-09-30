import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_official_response_batch_handoff as batch  # noqa: E402


class OfficialResponse20260916Tests(unittest.TestCase):
    def test_sanitized_batch_remains_fail_closed_for_position_semantics(self):
        value = json.loads((ROOT / "runtime/evidence/revenue-mvp-official-response-20260916.json").read_text(encoding="utf-8"))
        result = batch.handoff_batch(value)
        self.assertEqual(result.status, batch.RESPONSE_INCOMPLETE)
        self.assertEqual(result.lifecycle_status, "PARTIALLY_RESOLVED")
        self.assertEqual(result.lifecycle_resolved_question_count, 8)
        self.assertEqual(result.sort_status, "PARTIALLY_RESOLVED")
        self.assertEqual(result.sort_resolved_question_count, 4)
        self.assertEqual(result.total_unresolved_question_count, 5)
        self.assertFalse(result.combined_gate_review_candidate)
        self.assertFalse(result.gate_mutation_allowed)
        self.assertFalse(result.production_activation_allowed)


if __name__ == "__main__":
    unittest.main()
