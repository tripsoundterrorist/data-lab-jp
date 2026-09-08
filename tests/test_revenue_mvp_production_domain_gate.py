import inspect
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_production_domain_gate as gate  # noqa: E402


class RevenueMvpProductionDomainGateTests(unittest.TestCase):
    def test_current_state_requires_operator_confirmation(self):
        result = gate.assess(gate.current_evidence())
        self.assertEqual(result.status, gate.PENDING)
        self.assertFalse(result.condition_verified)
        self.assertFalse(result.gate_unlock_allowed)
        self.assertFalse(result.production_change_allowed)
        self.assertIn("CONFIRM_DMM_APPROVED_SITE_IN_ACCOUNT", result.next_actions)

    def test_complete_evidence_is_review_only(self):
        result = gate.assess(gate.DomainApprovalEvidence(True, True, False))
        self.assertEqual(result.status, gate.READY)
        self.assertTrue(result.condition_verified)
        self.assertFalse(result.gate_unlock_allowed)
        self.assertFalse(result.production_change_allowed)

    def test_pending_url_change_blocks(self):
        result = gate.assess(gate.DomainApprovalEvidence(True, True, True))
        self.assertEqual(result.status, gate.PENDING)
        self.assertIn("URL_CHANGE_APPLICATION_PENDING", result.reason_codes)

    def test_non_boolean_and_unknown_input_fail_closed(self):
        for value in (
            gate.DomainApprovalEvidence(1, True, False),
            {"approved_site_confirmed": True},
            None,
        ):
            with self.subTest(value=value):
                result = gate.assess(value)
                self.assertEqual(result.status, gate.FAIL_CLOSED)
                self.assertFalse(result.condition_verified)

    def test_contract_accepts_no_url_or_identifier(self):
        fields = set(inspect.signature(gate.DomainApprovalEvidence).parameters)
        self.assertFalse(any("url" in field and field != "url_change_application_pending" for field in fields))
        output = json.dumps(gate.assess(gate.current_evidence()).to_dict())
        self.assertNotIn("https://", output)
        self.assertNotIn("affiliate_id", output)


if __name__ == "__main__":
    unittest.main()
