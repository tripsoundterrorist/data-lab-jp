from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_cta_canonical_selection_preflight as preflight
import affiliate_cta_click_revalidation_candidate as candidate
import affiliate_cta_trusted_selection_bundle as trusted


NOW = datetime(2026, 9, 22, 5, 0, tzinfo=timezone.utc)
PUBLIC_ID = "itm_0123456789abcdef01234567"
AFFILIATE_URL = "https://al.dmm.co.jp/?lurl=https%3A%2F%2Fexample.dmm.co.jp%2F"
CONTENT_ID = "fixture-content-1"


def receipt(**changes):
    value = preflight.CanonicalSelectionReceipt(
        preflight.VERSION, trusted.CANONICALIZATION_VERSION, preflight.READY,
        trusted.SOURCE_DATABASE_SHA256, trusted.LIVE_ARTIFACT_SHA256,
        trusted.SELECTION_DIGEST, trusted.EXACT_SELECTION_COUNT,
        trusted.EXACT_SELECTION_COUNT, trusted.EXACT_SELECTION_COUNT,
    )
    return replace(value, **changes)


def bundle():
    value = trusted.from_canonical_preflight(receipt())
    assert value is not None
    return value


def resolver_observation(**changes):
    value = trusted.TrustedResolverObservation(
        PUBLIC_ID, trusted.SELECTION_DIGEST, NOW,
        "API_VISIBLE_AFFILIATE_PRESENT",
        {"result": {"status": 200, "items": [{"content_id": CONTENT_ID, "affiliateURL": AFFILIATE_URL}]}},
        CONTENT_ID,
    )
    return replace(value, **changes)


def resolver(value=resolver_observation()):
    return lambda _public_id, _bundle: value


def decide(**changes):
    values = {
        "version": candidate.VERSION,
        "clicked_public_id": PUBLIC_ID,
        "selection_bundle": bundle(),
        "trusted_resolver": resolver(),
        "evaluated_at": NOW,
    }
    values.update(changes)
    return candidate.decide(**values)


class ClickRevalidationCandidateTests(unittest.TestCase):
    def test_fresh_trusted_bundle_yields_bodyless_nonactivating_303_candidate(self):
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

    def test_caller_controlled_digest_and_selection_are_not_accepted(self):
        with self.assertRaises(TypeError):
            candidate.decide(version=candidate.VERSION, clicked_public_id=PUBLIC_ID,
                selection_bundle=bundle(), trusted_resolver=resolver(), evaluated_at=NOW,
                selection_digest="caller-controlled")
        self.assertEqual(decide(selection_bundle=replace(bundle(), selection_digest="wrong")).status, candidate.BLOCKED)

    def test_caller_observation_or_url_are_not_accepted(self):
        for name, value in (("observation", {}), ("affiliate_url", AFFILIATE_URL)):
            with self.subTest(name=name):
                with self.assertRaises(TypeError):
                    candidate.decide(version=candidate.VERSION, clicked_public_id=PUBLIC_ID,
                        selection_bundle=bundle(), trusted_resolver=resolver(), evaluated_at=NOW,
                        **{name: value})

    def test_missing_or_invalid_trusted_resolver_blocks(self):
        for value in (None, lambda _id, _bundle: {}, lambda _id, _bundle: None):
            with self.subTest(value=value):
                self.assertEqual(decide(trusted_resolver=value).status, candidate.BLOCKED)

    def test_trusted_resolver_is_called_once_without_retry(self):
        calls = 0
        def once(_id, _bundle):
            nonlocal calls
            calls += 1
            return resolver_observation()
        self.assertEqual(decide(trusted_resolver=once).status, candidate.ALLOWED)
        self.assertEqual(calls, 1)

    def test_bundle_tamper_blocks_before_resolver(self):
        called = False
        def should_not_run(_id, _bundle):
            nonlocal called
            called = True
            return resolver_observation()
        result = decide(selection_bundle=replace(bundle(), source_database_sha256="0" * 64), trusted_resolver=should_not_run)
        self.assertEqual(result.status, candidate.BLOCKED)
        self.assertFalse(called)

    def test_stale_future_error_rate_limit_and_missing_link_block(self):
        cases = (
            resolver_observation(checked_at=NOW - timedelta(minutes=16)),
            resolver_observation(checked_at=NOW + timedelta(seconds=1)),
            resolver_observation(eligibility_status="API_ERROR"),
            resolver_observation(eligibility_status="RATE_LIMITED"),
            resolver_observation(eligibility_status="API_VISIBLE_AFFILIATE_ABSENT"),
        )
        for value in cases:
            with self.subTest(value=value.eligibility_status):
                self.assertEqual(decide(trusted_resolver=resolver(value)).status, candidate.BLOCKED)

    def test_unsafe_urls_block_without_leaking_value(self):
        values = (
            "http://al.dmm.co.jp/x", "//al.dmm.co.jp/x", "https://user:pass@al.dmm.co.jp/x",
            "https://example.dmm.co.jp/x", "https://al.dmm.co.jp:443/x",
            "https://dmm.co.jp.example.invalid/x", "https://al.dmm.co.jp/x\r\nLocation:https://evil.invalid/",
        )
        for value in values:
            with self.subTest(value=value):
                response = {"result": {"status": 200, "items": [{"content_id": CONTENT_ID, "affiliateURL": value}]}}
                result = decide(trusted_resolver=resolver(resolver_observation(response=response)))
                self.assertEqual(result.status, candidate.BLOCKED)
                self.assertNotIn(value, str(result.to_dict()))


if __name__ == "__main__":
    unittest.main()
