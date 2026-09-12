from pathlib import Path
import ast
import json
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import temporal_active_runner_connection_design as design  # noqa: E402


class ActiveRunnerConnectionDesignTests(unittest.TestCase):
    def test_current_boundary_produces_design_only(self):
        result = design.assess_design()
        self.assertEqual(result.status, design.DESIGN_READY)
        self.assertTrue(result.design_authorized)
        self.assertEqual(result.required_boundaries, design.REQUIRED_BOUNDARIES)
        self.assertFalse(result.implementation_authorized)
        self.assertFalse(result.active_connection_authorized)
        self.assertFalse(result.api_request_authorized)
        self.assertFalse(result.state_write_authorized)
        self.assertFalse(result.scheduler_change_authorized)
        self.assertFalse(result.deploy_allowed)

    def test_unexpected_legacy_or_candidate_boundary_fails_closed(self):
        with mock.patch.object(design.inspect, "getsource", return_value="changed"):
            result = design.assess_design()
        self.assertEqual(result.status, design.BLOCKED)
        self.assertFalse(result.design_authorized)

    def test_safe_result_has_no_identifiers_paths_or_payloads(self):
        rendered = json.dumps(design.assess_design().to_dict()).casefold()
        for forbidden in ("content_id", "series-", "payloads", "c:\\\\", "/home/"):
            self.assertNotIn(forbidden, rendered)

    def test_design_module_has_no_execution_or_io_capability(self):
        tree = ast.parse(Path(design.__file__).read_text(encoding="utf-8"))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertFalse(imports & {
            "os", "pathlib", "subprocess", "tempfile", "urllib", "requests"
        })
        source = Path(design.__file__).read_text(encoding="utf-8")
        for forbidden in ("run_temporal_probe(", "execute_plan(", "persist_validated_bundle_for_test("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
