from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import affiliate_cta_approved_context as approved
import affiliate_cta_canary_offline_candidate as candidate
import affiliate_cta_production_composition as composition

NOW = datetime(2026, 9, 22, 4, 0, tzinfo=timezone.utc)
IDS = tuple(f"itm_{value:024x}" for value in range(10))
URL = "https://al.fanza.co.jp/?lurl=https%3A%2F%2Fexample.dmm.co.jp%2F"
CONTEXT = approved._make_test_context(IDS, lambda _value: None)
DIGEST = approved.exact.canonical_digest(IDS)


def record(value, observation=None):
    obs = observation or approved._InternalObservation(
        value, DIGEST, NOW, "fixture-" + value[-1],
        {"result": {"status": 200, "items": [{"content_id": "fixture-" + value[-1], "affiliateURL": URL}]}},
    )
    return approved._InternalPresentationRecord(value, DIGEST, "<fixture>", obs)


def render(records, context=CONTEXT, provider=None):
    provider = provider or (lambda _context: records)
    lifecycle = composition._build_offline_composition_for_test(CONTEXT, {pid: "content-"+str(i) for i,pid in enumerate(IDS)}, lambda request: None, lambda: NOW)
    if not approved._context_valid(context):
        lifecycle = replace(lifecycle, context=context)
    def bound(_context):
        source = provider(context)
        return tuple(replace(item, observation=replace(item.observation, context=lifecycle.context,
                     provider=lifecycle.provider, lease=lifecycle.lease, generation=lifecycle.generation))
                     if type(item) is approved._InternalPresentationRecord else item for item in source)
    with mock.patch.object(composition, "production_provider", return_value=lifecycle), \
         mock.patch.object(composition._OfflineComposition, "records", side_effect=bound):
        return candidate.render(as_of=NOW)


class CandidateTests(unittest.TestCase):
    def test_exact_verified_records_render_safe_inert_ctas(self):
        result = render(tuple(record(value) for value in IDS))
        self.assertEqual(result.cta_count, 10)
        self.assertIn("&lt;fixture&gt;", result.html)
        self.assertIn('rel="noopener noreferrer sponsored"', result.html)
        self.assertIn("PR：", result.html)
        self.assertTrue(all(value is False for value in (
            result.publication_allowed, result.affiliate_eligibility_allowed,
            result.gate_mutation_allowed, result.cta_activation_allowed,
        )))

    def test_missing_or_invalid_context_never_calls_provider(self):
        calls = []
        provider = lambda context: calls.append(context) or ()
        for value in (None, replace(CONTEXT, selection_digest="wrong")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    render((), context=value, provider=provider)
        self.assertEqual(calls, [])

    def test_invalid_complete_set_never_evaluates_observation(self):
        exact = tuple(record(value) for value in IDS)
        cases = (
            exact[:-1], exact[:-1] + (exact[0],),
            exact + (record("itm_00000000000000000000000a"),),
            tuple(replace(value, selection_digest="wrong") for value in exact),
            tuple(replace(value, title="") if index == 9 else value for index, value in enumerate(exact)),
        )
        for value in cases:
            with self.subTest(value=len(value)):
                with mock.patch.object(candidate.click, "_decide", wraps=candidate.click._decide) as evaluated:
                    with self.assertRaises(ValueError):
                        render(value)
                    self.assertEqual(evaluated.call_count, 0)

    def test_provider_once_and_each_observation_once_after_complete_validation(self):
        calls, records = [], tuple(record(value) for value in IDS)
        def provider(context):
            calls.append(context)
            return records
        with mock.patch.object(candidate.click, "_decide", wraps=candidate.click._decide) as evaluated:
            result = render(records, provider=provider)
        self.assertEqual(result.cta_count, 10)
        self.assertEqual(calls, [CONTEXT])
        self.assertEqual(evaluated.call_count, 10)

    def test_invalid_observation_is_non_display_not_activation(self):
        stale = record(IDS[0], replace(record(IDS[0]).observation, checked_at=NOW - timedelta(minutes=16)))
        result = render((stale,) + tuple(record(value) for value in IDS[1:]))
        self.assertEqual(result.cta_count, 9)
        self.assertNotIn('/go/' + IDS[0], result.html)

    def test_public_render_rejects_records_digest_and_provider_injection(self):
        for name, value in (("records", ()), ("selection_digest", "x"), ("provider", lambda: ())):
            with self.subTest(name=name):
                with self.assertRaises(TypeError):
                    candidate.render(as_of=NOW, **{name: value})


if __name__ == "__main__":
    unittest.main()
