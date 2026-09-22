from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_cta_approved_context as approved
import affiliate_cta_click_revalidation_candidate as candidate

NOW = datetime(2026, 9, 22, 5, 0, tzinfo=timezone.utc)
IDS = tuple(f"itm_{value:024x}" for value in range(10))
URL = "https://al.dmm.co.jp/?lurl=https%3A%2F%2Fexample.dmm.co.jp%2F"


def observation(public_id=IDS[0]):
    return {"public_id": public_id, "checked_at": NOW,
        "eligibility_status": "API_VISIBLE_AFFILIATE_PRESENT",
        "resolved_content_id": "fixture-content-1",
        "response": {"result": {"status": 200, "items": [{"content_id": "fixture-content-1", "affiliateURL": URL}]}}}


def test_context(observe=lambda value: observation(value)):
    return approved._make_test_context(IDS, observe)


def dry(**changes):
    values = {"version": candidate.VERSION, "clicked_public_id": IDS[0], "evaluated_at": NOW}
    values.update(changes)
    context = values.pop("context", test_context())
    observe = context.observe if type(context) is approved._TestOnlyApprovedContext else None
    with mock.patch.object(approved, "production_context", return_value=context), \
         mock.patch.object(approved, "production_observe", observe):
        return candidate.decide(**values)


class ClickRevalidationCandidateTests(unittest.TestCase):
    def test_normal_internal_dry_assessment_is_bodyless_nonactivating_303_candidate(self):
        result = dry()
        self.assertEqual(result.status, candidate.ALLOWED)
        self.assertEqual(result.redirect_status_candidate, 303)
        self.assertNotIn(IDS[0], str(result.to_dict()))
        self.assertNotIn(URL, str(result.to_dict()))
        self.assertFalse(result.redirect_activation_allowed)

    def test_production_api_rejects_caller_injected_digest_list_url_observation_and_resolver(self):
        for name, value in (("selection_digest", "x"), ("selected_public_ids", IDS),
                            ("observation", observation()), ("affiliate_url", URL),
                            ("trusted_resolver", lambda _value: observation())):
            with self.subTest(name=name):
                with self.assertRaises(TypeError):
                    candidate.decide(version=candidate.VERSION, clicked_public_id=IDS[0],
                        evaluated_at=NOW, **{name: value})
        self.assertEqual(candidate.decide(version=candidate.VERSION, clicked_public_id=IDS[0], evaluated_at=NOW).status, candidate.BLOCKED)

    def test_every_outside_id_blocks_before_resolver(self):
        calls = 0
        def observe(_value):
            nonlocal calls
            calls += 1
            return observation()
        context = test_context(observe)
        outside = tuple(f"itm_{value:024x}" for value in range(10, 21))
        for value in outside:
            self.assertEqual(dry(clicked_public_id=value, context=context).status, candidate.BLOCKED)
        self.assertEqual(calls, 0)

    def test_synthetic_observation_is_unreachable_from_production_entrypoint(self):
        self.assertEqual(
            candidate.decide(version=candidate.VERSION, clicked_public_id=IDS[0], evaluated_at=NOW).status,
            candidate.BLOCKED,
        )
        self.assertEqual(dry(context={}).status, candidate.BLOCKED)

    def test_invalid_or_stale_test_observation_blocks(self):
        for value in (None, {}, {**observation(), "checked_at": NOW.replace(year=2025)},
                      {**observation(), "eligibility_status": "RATE_LIMITED"}):
            with self.subTest(value=value):
                self.assertEqual(dry(context=test_context(lambda _id: value)).status, candidate.BLOCKED)


if __name__ == "__main__":
    unittest.main()
