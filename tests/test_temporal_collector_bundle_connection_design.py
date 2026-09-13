from pathlib import Path
import json
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import temporal_collector_bundle_connection_design as design  # noqa: E402


class CollectorBundleConnectionDesignTests(unittest.TestCase):
    def test_current_design_identifies_required_isolated_bridge(self):
        result = design.assess_design()
        self.assertEqual(result.status, design.READY)
        self.assertTrue(result.fixed_populations_verified)
        self.assertTrue(result.bundle_contract_verified)
        self.assertTrue(result.approved_connection_contract_verified)
        self.assertFalse(result.legacy_date_collector_reusable)
        self.assertFalse(result.legacy_response_adapter_reusable)
        self.assertEqual(result.next_gate, design.NEXT_GATE)
        self.assertFalse(result.implementation_authorized)
        self.assertFalse(result.api_request_authorized)
        self.assertFalse(result.state_write_authorized)
        self.assertFalse(result.scheduler_change_authorized)
        self.assertFalse(result.production_write_authorized)
        self.assertFalse(result.deploy_allowed)

    def test_changed_bundle_contract_blocks(self):
        with mock.patch.object(
            design.bundle_adapter,
            "PAYLOAD_FIELDS",
            frozenset({"content_id", "raw_response"}),
        ):
            result = design.assess_design()
        self.assertEqual(result.status, design.BLOCKED)
        self.assertIsNone(result.next_gate)

    def test_missing_collector_source_fails_closed_without_detail(self):
        with mock.patch.object(Path, "read_text", side_effect=OSError("private-path")):
            result = design.assess_design()
        rendered = json.dumps(result.to_dict())
        self.assertEqual(result.status, design.BLOCKED)
        self.assertNotIn("private-path", rendered)


if __name__ == "__main__":
    unittest.main()
