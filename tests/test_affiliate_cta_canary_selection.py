from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_cta_canary_plan as plan_module
import affiliate_cta_canary_selection as selection
from product_verification import Observation, VerificationObservation


NOW = datetime(2026, 9, 22, 3, 0, tzinfo=timezone.utc)


def observation(*, visible=True, affiliate=True, minutes_old=1):
    return VerificationObservation(
        observation=Observation.API_ITEM_VISIBLE if visible else Observation.API_ITEM_NOT_RETURNED,
        observed_at=NOW - timedelta(minutes=minutes_old),
        expected_content_id_match=True if visible else False,
        affiliate_link_observed=affiliate if visible else None,
        source_status_code=200,
        reason_codes=("SANITIZED_TEST_OBSERVATION",),
    )


def candidate(index=0, **kwargs):
    return selection.CandidateObservation(
        public_id=f"itm_{index:024x}", verification=observation(**kwargs)
    )


class AffiliateCtaCanarySelectionTests(unittest.TestCase):
    def setUp(self):
        self.plan = plan_module.current_plan()
        self.assertEqual(self.plan.status, plan_module.READY)

    def test_ten_fresh_eligible_items_yield_counts_only(self):
        result = selection.select(
            tuple(candidate(index) for index in range(10)), as_of=NOW, plan=self.plan
        )
        self.assertEqual(result.status, selection.READY)
        self.assertEqual(result.selected_count, 10)
        self.assertTrue(result.click_time_revalidation_required)
        self.assertFalse(result.static_affiliate_url_allowed)
        self.assertFalse(result.identifiers_exposed)
        self.assertFalse(result.cta_activation_allowed)
        self.assertFalse(result.d1_write_allowed)
        self.assertFalse(result.deployment_allowed)
        self.assertNotIn("itm_", str(result.to_dict()))

    def test_missing_item_or_affiliate_url_blocks_entire_set(self):
        for bad in (candidate(9, visible=False), candidate(9, affiliate=False)):
            values = tuple(candidate(index) for index in range(9)) + (bad,)
            result = selection.select(values, as_of=NOW, plan=self.plan)
            self.assertEqual(result.status, selection.BLOCKED)
            self.assertEqual(result.selected_count, 0)

    def test_stale_future_duplicate_and_oversized_sets_block(self):
        cases = (
            (candidate(0, minutes_old=16),),
            (candidate(0, minutes_old=-1),),
            (candidate(0), candidate(0)),
            tuple(candidate(index) for index in range(11)),
        )
        for values in cases:
            with self.subTest(size=len(values)):
                result = selection.select(values, as_of=NOW, plan=self.plan)
                self.assertEqual(result.status, selection.BLOCKED)
                self.assertFalse(result.cta_activation_allowed)

    def test_open_or_malformed_plan_is_rejected(self):
        opened = replace(self.plan, cta_activation_allowed=True)
        for value in (opened, None, {}):
            with self.subTest(value=value):
                result = selection.select((candidate(0),), as_of=NOW, plan=value)
                self.assertEqual(result.status, selection.BLOCKED)


if __name__ == "__main__":
    unittest.main()

