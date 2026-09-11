from dataclasses import fields, replace
from pathlib import Path
import ast
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import temporal_validated_bundle_persistence_review as subject  # noqa: E402


def evidence():
    return subject.Evidence(subject.VERSION, True, True, True, True, True, True, False)


class IsolatedConnectionReviewTests(unittest.TestCase):
    def test_complete_evidence_authorizes_nothing(self):
        result = subject.review(evidence())
        self.assertEqual(result.status, "REVIEW_READY_FOR_EXPLICIT_APPROVAL")
        self.assertEqual(result.unmet_areas, ())
        self.assertFalse(result.active_connection_authorized)
        self.assertFalse(result.production_write_authorized)
        self.assertFalse(result.deploy_allowed)

    def test_each_missing_area_blocks(self):
        names = [f.name for f in fields(subject.Evidence)
                 if f.name not in {"version", "approval_granted"}]
        for name, area in zip(names, subject.AREAS):
            result = subject.review(replace(evidence(), **{name: False}))
            self.assertEqual(result.status, "REVIEW_BLOCKED")
            self.assertEqual(result.unmet_areas, (area,))

    def test_invalid_and_approval_input_block(self):
        for value in (None, {}, replace(evidence(), version="9"),
                      replace(evidence(), safe_result=1),
                      replace(evidence(), approval_granted=True)):
            self.assertEqual(subject.review(value).status, "REVIEW_BLOCKED")

    def test_reviewer_has_no_io_capability(self):
        tree = ast.parse(Path(subject.__file__).read_text(encoding="utf-8"))
        imports = {a.name for n in ast.walk(tree)
                   if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
        self.assertFalse(imports & {"os", "pathlib", "subprocess", "tempfile", "requests"})


if __name__ == "__main__":
    unittest.main()
