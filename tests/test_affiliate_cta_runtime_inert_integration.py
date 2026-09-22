from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_cta_canonical_selection_preflight as preflight
import affiliate_cta_click_revalidation_candidate as click
import affiliate_cta_runtime_inert_integration as integration
import affiliate_cta_trusted_selection_bundle as trusted


NOW = datetime(2026, 9, 22, 6, 0, tzinfo=timezone.utc)
PUBLIC_ID = "itm_0123456789abcdef01234567"
URL = "https://al.fanza.co.jp/?lurl=https%3A%2F%2Fwww.dmm.co.jp%2F"
CONTENT_ID = "fixture-content-1"
def bundle():
    receipt = preflight.CanonicalSelectionReceipt(
        preflight.VERSION, trusted.CANONICALIZATION_VERSION, preflight.READY,
        trusted.SOURCE_DATABASE_SHA256, trusted.LIVE_ARTIFACT_SHA256,
        trusted.SELECTION_DIGEST, 10, 10, 10,
    )
    value = trusted.from_canonical_preflight(receipt)
    assert value is not None
    return value


def observation(**changes):
    value = trusted.TrustedResolverObservation(
        PUBLIC_ID, trusted.SELECTION_DIGEST, NOW, "API_VISIBLE_AFFILIATE_PRESENT",
        {"result":{"status":200,"items":[{"content_id":CONTENT_ID,"affiliateURL":URL}]}}, CONTENT_ID,
    )
    return replace(value, **changes)


def assess(**changes):
    values = {
        "version": integration.VERSION,
        "method": "GET",
        "path": "/go/" + PUBLIC_ID,
        "request_body_present": False,
        "official_answer_candidate": True,
        "publication_gate_overall_eligible": True,
        "runtime_chain_connected": True,
        "rate_limit_allowed": True,
        "pr_disclosure_available": True,
        "selection_bundle": bundle(),
        "trusted_resolver": lambda _public_id, _bundle: observation(),
        "evaluated_at": NOW,
    }
    values.update(changes)
    return integration.assess(**values)


class InertIntegrationTests(unittest.TestCase):
    def test_exact_fresh_candidate_is_review_ready_but_cannot_activate(self):
        result = assess()
        self.assertEqual(result.status, integration.READY)
        self.assertEqual(result.response_status_candidate, 303)
        self.assertTrue(result.route_assessed)
        self.assertTrue(result.click_revalidation_assessed)
        self.assertFalse(result.redirect_location_present)
        self.assertFalse(result.redirect_activation_allowed)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.gate_mutation_allowed)
        self.assertFalse(result.production_write_performed)
        serialized = str(result.to_dict())
        self.assertNotIn(PUBLIC_ID, serialized)
        self.assertNotIn(URL, serialized)

    def test_closed_route_guards_stop_before_click_assessment(self):
        for change in (
            {"publication_gate_overall_eligible": False},
            {"runtime_chain_connected": False},
            {"rate_limit_allowed": False},
            {"pr_disclosure_available": False},
            {"method": "POST"},
            {"path": "/go/not-valid"},
        ):
            with self.subTest(change=change):
                result = assess(**change)
                self.assertEqual(result.status, integration.BLOCKED)
                self.assertFalse(result.click_revalidation_assessed)

    def test_click_failures_never_produce_redirect_candidate(self):
        for change in (
            {"selection_bundle": replace(bundle(), selection_digest="wrong")},
            {"trusted_resolver": lambda _public_id, _bundle: observation(checked_at=NOW - timedelta(minutes=16))},
            {"trusted_resolver": lambda _public_id, _bundle: observation(eligibility_status="RATE_LIMITED")},
            {"trusted_resolver": lambda _public_id, _bundle: observation(response={"result":{"status":200,"items":[{"content_id":CONTENT_ID,"affiliateURL":"https://evil.invalid/"}]}})},
        ):
            with self.subTest(change=change):
                result = assess(**change)
                self.assertEqual(result.status, integration.BLOCKED)
                self.assertTrue(result.click_revalidation_assessed)
                self.assertIsNone(result.response_status_candidate)
                self.assertFalse(result.redirect_location_present)


if __name__ == "__main__":
    unittest.main()
