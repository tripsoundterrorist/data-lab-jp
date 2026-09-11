from dataclasses import fields, replace
from pathlib import Path
import ast
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import temporal_filesystem_persistence_review as review  # noqa: E402


def evidence():
    return review.PersistenceCandidateEvidence(
        review.VERSION, True, True, True, True, True, True, True, True, True, False,
    )


class PersistenceCandidateReviewTests(unittest.TestCase):
    def test_complete_evidence_is_ready_but_authorizes_nothing(self):
        result = review.review_persistence_candidate(evidence())
        self.assertEqual(result.status, review.REVIEW_READY_FOR_EXPLICIT_APPROVAL)
        self.assertEqual(result.unmet_areas, ())
        self.assertFalse(result.filesystem_connection_authorized)
        self.assertFalse(result.production_write_authorized)
        self.assertFalse(result.deploy_allowed)

    def test_each_missing_area_blocks(self):
        names = [field.name for field in fields(review.PersistenceCandidateEvidence)
                 if field.name not in {"version", "explicit_approval_granted"}]
        for name, area in zip(names, review.REVIEW_AREAS):
            with self.subTest(area=area):
                result = review.review_persistence_candidate(
                    replace(evidence(), **{name: False})
                )
                self.assertEqual(result.status, review.REVIEW_BLOCKED)
                self.assertEqual(result.unmet_areas, (area,))

    def test_invalid_or_approval_bearing_input_blocks(self):
        for value in (None, {}, True, replace(evidence(), version="9"),
                      replace(evidence(), explicit_approval_granted=True),
                      replace(evidence(), result_redaction_verified=1)):
            with self.subTest(value=value):
                self.assertEqual(
                    review.review_persistence_candidate(value).status,
                    review.REVIEW_BLOCKED,
                )

    def test_reviewer_has_no_io_or_activation_capability(self):
        source = Path(review.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {
            alias.name for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names
        }
        calls = {
            node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(tree) if isinstance(node, ast.Call)
            and isinstance(node.func, (ast.Attribute, ast.Name))
        }
        self.assertFalse(imports & {"os", "pathlib", "subprocess", "tempfile", "requests"})
        self.assertFalse(calls & {"open", "mkdir", "replace", "write_bytes", "read_bytes"})


if __name__ == "__main__":
    unittest.main()
