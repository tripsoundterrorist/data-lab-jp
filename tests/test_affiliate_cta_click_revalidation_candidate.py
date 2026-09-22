from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_cta_click_revalidation_candidate as candidate
import affiliate_cta_exact_selection as exact_selection


NOW = datetime(2026, 9, 22, 5, 0, tzinfo=timezone.utc)
PUBLIC_ID = "itm_0123456789abcdef01234567"
AFFILIATE_URL = "https://al.dmm.co.jp/?lurl=https%3A%2F%2Fexample.dmm.co.jp%2F"
CONTENT_ID = "fixture-content-1"
DIGEST = exact_selection.canonical_digest((PUBLIC_ID,))


def observation(**changes):
    value = {
        "public_id": PUBLIC_ID,
        "checked_at": NOW,
        "status": "API_VISIBLE_AFFILIATE_PRESENT",
        "response": {"result": {"status": 200, "items": [{"content_id": CONTENT_ID, "affiliateURL": AFFILIATE_URL}]}},
    }
    value.update(changes)
    return value


def decide(**changes):
    values = {
        "version": candidate.VERSION,
        "selection_digest": DIGEST,
        "selected_public_ids": (PUBLIC_ID,),
        "clicked_public_id": PUBLIC_ID,
        "resolve_content_id": lambda value: CONTENT_ID if value == PUBLIC_ID else None,
        "observation": observation(),
        "evaluated_at": NOW,
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
            {"observation": observation(checked_at=NOW - timedelta(minutes=16))},
            {"observation": observation(checked_at=NOW + timedelta(seconds=1))},
            {"observation": observation(status="API_ERROR")},
            {"observation": observation(status="RATE_LIMITED")},
            {"observation": observation(status="API_VISIBLE_AFFILIATE_ABSENT")},
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
                result = decide(observation=observation(response={"result":{"status":200,"items":[{"content_id":CONTENT_ID,"affiliateURL":value}]}}))
                self.assertEqual(result.status, candidate.BLOCKED)
                self.assertNotIn(value, str(result.to_dict()))

    def test_observation_must_bind_clicked_id_resolved_item_and_url(self):
        other = "itm_abcdef0123456789abcdef01"
        cases = (
            observation(public_id=other),
            observation(response={"result":{"status":200,"items":[{"content_id":"other","affiliateURL":AFFILIATE_URL}]}}),
            observation(response={"result":{"status":200,"items":[{"content_id":CONTENT_ID,"affiliateURL":AFFILIATE_URL},{"content_id":CONTENT_ID,"affiliateURL":AFFILIATE_URL}]}}),
        )
        for value in cases:
            with self.subTest(value=value):
                self.assertEqual(decide(observation=value).status, candidate.BLOCKED)

    def test_resolver_failure_or_mismatch_blocks(self):
        def failing(_value):
            raise RuntimeError("blocked")
        for resolver in (None, failing, lambda _value: "other-content"):
            with self.subTest(resolver=resolver):
                self.assertEqual(decide(resolve_content_id=resolver).status, candidate.BLOCKED)


if __name__ == "__main__":
    unittest.main()
