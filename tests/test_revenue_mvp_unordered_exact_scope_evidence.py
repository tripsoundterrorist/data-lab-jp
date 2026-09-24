from pathlib import Path
import json
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_unordered_exact_scope_evidence as evidence  # noqa: E402


class UnorderedExactScopeEvidenceTests(unittest.TestCase):
    def test_current_exact_scope_is_ready_without_activation(self):
        result = evidence.assess_evidence()
        self.assertEqual(result.status, evidence.READY)
        self.assertTrue(result.exact_scope_verified)
        self.assertFalse(result.additional_lifecycle_sort_inquiry_required)
        self.assertTrue(result.expanded_scope_requires_new_review)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_activation_allowed)
        self.assertFalse(result.affiliate_eligibility_allowed)
        self.assertFalse(result.gate_mutation_allowed)

    def test_scope_expansion_or_permissive_flag_fails_closed(self):
        for key, value in (
            ("allowed_fields", ["title", "rank"]),
            ("excluded_topics", []),
            ("expanded_scope_requires_new_review", False),
            ("publication_allowed", True),
            ("gate_mutation_allowed", True),
        ):
            payload = json.loads(evidence.EVIDENCE.read_text(encoding="utf-8"))
            payload[key] = value
            path = mock.Mock()
            path.read_text.return_value = json.dumps(payload)
            with self.subTest(key=key), mock.patch.object(evidence, "EVIDENCE", path):
                result = evidence.assess_evidence()
            self.assertEqual(result.status, evidence.BLOCKED)
            self.assertTrue(result.additional_lifecycle_sort_inquiry_required)
            self.assertFalse(result.gate_mutation_allowed)

    def test_invalid_input_is_sanitized(self):
        path = mock.Mock()
        path.read_text.side_effect = OSError("private path")
        with mock.patch.object(evidence, "EVIDENCE", path):
            result = evidence.assess_evidence()
        self.assertNotIn("private", json.dumps(result.to_dict()).casefold())


if __name__ == "__main__":
    unittest.main()
