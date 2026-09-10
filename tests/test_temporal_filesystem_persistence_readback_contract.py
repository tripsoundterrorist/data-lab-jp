import ast
from dataclasses import fields, replace
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import temporal_filesystem_persistence_readback_contract as contract  # noqa: E402


def evidence():
    return contract.PersistenceReadbackEvidence(True, True, True, True, True, True, True)


class PersistenceReadbackContractTests(unittest.TestCase):
    def test_complete_contract_is_review_only(self):
        result = contract.evaluate(evidence())
        self.assertEqual(result.status, "CONTRACT_READY_FOR_REVIEW")
        self.assertEqual((result.max_document_bytes, result.max_writes_per_run,
                          result.retention_days), (1024 * 1024, 4, 45))
        self.assertFalse(result.filesystem_access_performed)
        self.assertFalse(result.write_authorized)
        self.assertFalse(result.connection_authorized)

    def test_each_missing_area_blocks(self):
        for field in fields(contract.PersistenceReadbackEvidence):
            with self.subTest(field=field.name):
                self.assertEqual(contract.evaluate(
                    replace(evidence(), **{field.name: False})).status,
                    "CONTRACT_BLOCKED")

    def test_wrong_types_and_unknown_input_block(self):
        for value in (None, {}, True):
            self.assertEqual(contract.evaluate(value).status, "CONTRACT_BLOCKED")

    def test_module_has_no_filesystem_capability(self):
        source = Path(contract.__file__).read_text(encoding="utf-8")
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
        self.assertFalse(imports & {"os", "pathlib", "shutil", "tempfile"})
        self.assertFalse(calls & {"open", "write_bytes", "write_text", "replace",
                                  "mkdir", "read_bytes", "read_text"})


if __name__ == "__main__":
    unittest.main()
