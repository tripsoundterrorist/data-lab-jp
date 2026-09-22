from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_cta_click_revalidation_candidate as candidate


NOW = datetime(2026, 9, 22, 5, 0, tzinfo=timezone.utc)
PUBLIC_ID = "itm_0123456789abcdef01234567"
AFFILIATE_URL = "https://al.dmm.co.jp/?lurl=https%3A%2F%2Fexample.dmm.co.jp%2F"


def decide(**changes):
    values = {
        "version": candidate.VERSION,
        "selection_digest": candidate.SELECTION_DIGEST,
        "selected_public_ids": (PUBLIC_ID,),
        "clicked_public_id": PUBLIC_ID,
        "revalidation_status": "API_VISIBLE_AFFILIATE_PRESENT",
        "checked_at": NOW,
        "evaluated_at": NOW,
        "affiliate_url": AFFILIATE_URL,
    }
    values.update(changes)
    return candidate.decide(**values)


class ClickRevalidationCandidateTests(unittest.TestCase):
    def test_fresh_exact_selection_yields_bodyless_nonactivating_303_candidate(self):
        result = decide()
        self.assertEqual(result.status, candidate.ALLOWED)
        self.assertEqual(result.redirect_status_candidate, 303)
        self.assertFalse(result.redirect_location_present)
        self.assertFalse(result.redirect_activation_allowed)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.gate_mutation_allowed)
        self.assertFalse(result.production_write_performed)
        serialized = str(result.to_dict())
        self.assertNotIn(PUBLIC_ID, serialized)
        self.assertNotIn(AFFILIATE_URL, serialized)

    def test_selection_contract_failures_block(self):
        other = "itm_abcdef0123456789abcdef01"
        cases = (
            {"selection_digest": "wrong"},
            {"selected_public_ids": ()},
            {"selected_public_ids": tuple(PUBLIC_ID for _ in range(11))},
            {"selected_public_ids": (PUBLIC_ID, PUBLIC_ID)},
            {"selected_public_ids": (other,)},
            {"clicked_public_id": "../bad"},
        )
        for values in cases:
            with self.subTest(values=values):
                self.assertEqual(decide(**values).status, candidate.BLOCKED)

    def test_stale_future_error_rate_limit_and_missing_link_block(self):
        cases = (
            {"checked_at": NOW - timedelta(minutes=16)},
            {"checked_at": NOW + timedelta(seconds=1)},
            {"revalidation_status": "API_ERROR"},
            {"revalidation_status": "RATE_LIMITED"},
            {"revalidation_status": "API_VISIBLE_AFFILIATE_ABSENT", "affiliate_url": None},
        )
        for values in cases:
            with self.subTest(values=values):
                self.assertEqual(decide(**values).status, candidate.BLOCKED)

    def test_unsafe_urls_block_without_leaking_value(self):
        values = (
            "http://al.dmm.co.jp/x",
            "//al.dmm.co.jp/x",
            "https://user:pass@al.dmm.co.jp/x",
            "https://example.dmm.co.jp/x",
            "https://al.dmm.co.jp:443/x",
            "https://dmm.co.jp.example.invalid/x",
            "https://al.dmm.co.jp/x\r\nLocation:https://evil.invalid/",
        )
        for value in values:
            with self.subTest(value=value):
                result = decide(affiliate_url=value)
                self.assertEqual(result.status, candidate.BLOCKED)
                self.assertNotIn(value, str(result.to_dict()))


if __name__ == "__main__":
    unittest.main()
