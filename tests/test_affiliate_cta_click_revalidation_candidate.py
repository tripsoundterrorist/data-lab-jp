from datetime import datetime, timedelta, timezone
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"scripts"))
import affiliate_cta_approved_context as approved
import affiliate_cta_click_revalidation_candidate as candidate

NOW=datetime(2026,9,22,5,0,tzinfo=timezone.utc)
IDS=tuple(f"itm_{value:024x}" for value in range(10))
URL="https://al.dmm.co.jp/?lurl=https%3A%2F%2Fexample.dmm.co.jp%2F"


def context(observe): return approved._make_test_context(IDS,observe)
def observation(public_id=IDS[0], **changes):
 value=approved._InternalObservation(public_id,approved.exact.canonical_digest(IDS),NOW,"fixture-content-1",{"result":{"status":200,"items":[{"content_id":"fixture-content-1","affiliateURL":URL}]}})
 return changes.get("value", value)
def decide(observe=lambda value: observation(value), **changes):
 value=context(observe)
 value=changes.pop("context",value)
 kwargs={"version":candidate.VERSION,"clicked_public_id":IDS[0],"evaluated_at":NOW}
 kwargs.update(changes)
 with mock.patch.object(approved,"production_context",return_value=value),mock.patch.object(approved,"production_observe",observe): return candidate.decide(**kwargs)


class ClickTests(unittest.TestCase):
 def test_provider_runs_once_after_membership_and_returns_inert_candidate(self):
  calls=[]
  result=decide(lambda value: calls.append(value) or observation(value))
  self.assertEqual(result.status,candidate.ALLOWED);self.assertEqual(calls,[IDS[0]])
  self.assertFalse(result.redirect_activation_allowed);self.assertNotIn(URL,str(result.to_dict()))
 def test_outside_eleven_never_call_provider(self):
  calls=[]
  for value in tuple(f"itm_{number:024x}" for number in range(10,21)):
   self.assertEqual(decide(lambda item:calls.append(item) or observation(item),clicked_public_id=value).status,candidate.BLOCKED)
  self.assertEqual(calls,[])
 def test_context_digest_mismatch_blocks_before_provider(self):
  calls=[]
  invalid=replace(context(lambda value:calls.append(value) or observation(value)),selection_digest="wrong")
  self.assertEqual(decide(lambda value:calls.append(value) or observation(value),context=invalid).status,candidate.BLOCKED)
  self.assertEqual(calls,[])
 def test_missing_exception_rate_limit_stale_future_mismatch_and_bad_url_block(self):
  variants=(
   lambda _value:None,lambda _value:(_ for _ in ()).throw(RuntimeError()),
   lambda value: approved._InternalObservation(value,approved.exact.canonical_digest(IDS),NOW-timedelta(minutes=16),"fixture-content-1",{"result":{"status":200,"items":[]}}),
   lambda value: approved._InternalObservation(value,approved.exact.canonical_digest(IDS),NOW+timedelta(seconds=1),"fixture-content-1",{"result":{"status":200,"items":[]}}),
   lambda value: approved._InternalObservation(value,approved.exact.canonical_digest(IDS),NOW,"other",{"result":{"status":200,"items":[{"content_id":"fixture-content-1","affiliateURL":URL}]}}),
   lambda value: approved._InternalObservation(value,approved.exact.canonical_digest(IDS),NOW,"fixture-content-1",{"result":{"status":429,"items":[]}}),
   lambda value: approved._InternalObservation(value,approved.exact.canonical_digest(IDS),NOW,"fixture-content-1",{"result":{"status":200,"items":[{"content_id":"fixture-content-1","affiliateURL":"https://evil.invalid/"}]}}),)
  for provider in variants:
   with self.subTest(provider=provider):self.assertEqual(decide(provider).status,candidate.BLOCKED)
 def test_public_entry_rejects_injection(self):
  for name,value in (("provider",lambda _value:None),("observation",{}),("affiliate_url",URL),("selection_digest","x")):
   with self.subTest(name=name):
    with self.assertRaises(TypeError):candidate.decide(version=candidate.VERSION,clicked_public_id=IDS[0],evaluated_at=NOW,**{name:value})

if __name__=='__main__':unittest.main()
