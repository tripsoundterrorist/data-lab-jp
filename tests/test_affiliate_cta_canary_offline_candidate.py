from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"scripts"))
import affiliate_cta_approved_context as approved
import affiliate_cta_canary_offline_candidate as candidate

NOW=datetime(2026,9,22,4,0,tzinfo=timezone.utc)
IDS=tuple(f"itm_{value:024x}" for value in range(10))
URL="https://al.fanza.co.jp/?lurl=https%3A%2F%2Fexample.dmm.co.jp%2F"
CONTEXT=approved._make_test_context(IDS,lambda _value:None)
DIGEST=approved.exact.canonical_digest(IDS)

def record(value, observation=None):
 obs=observation or approved._InternalObservation(value,DIGEST,NOW,"fixture-"+value[-1],{"result":{"status":200,"items":[{"content_id":"fixture-"+value[-1],"affiliateURL":URL}]}})
 return approved._InternalPresentationRecord(value,DIGEST,"<fixture>",obs)
def render(records):
 with mock.patch.object(approved,"production_context",return_value=CONTEXT),mock.patch.object(approved,"production_render_records",return_value=records):return candidate.render(as_of=NOW)

class CandidateTests(unittest.TestCase):
 def test_exact_verified_records_render_safe_inert_ctas(self):
  result=render(tuple(record(value) for value in IDS))
  self.assertEqual(result.cta_count,10);self.assertIn("&lt;fixture&gt;",result.html)
  self.assertIn('rel="noopener noreferrer sponsored"',result.html);self.assertIn("PR：",result.html)
  self.assertTrue(all(value is False for value in (result.publication_allowed,result.affiliate_eligibility_allowed,result.gate_mutation_allowed,result.cta_activation_allowed)))
 def test_partial_duplicate_extra_or_digest_mismatch_rejected(self):
  exact=tuple(record(value) for value in IDS)
  cases=(exact[:-1],exact[:-1]+(exact[0],),exact+(record("itm_00000000000000000000000a"),),tuple(replace(value,selection_digest="wrong") for value in exact))
  for value in cases:
   with self.subTest(value=len(value)):
    with self.assertRaises(ValueError):render(value)
 def test_invalid_observation_is_non_display_not_activation(self):
  stale=record(IDS[0],replace(record(IDS[0]).observation,checked_at=NOW-timedelta(minutes=16)))
  result=render((stale,)+tuple(record(value) for value in IDS[1:]))
  self.assertEqual(result.cta_count,9);self.assertNotIn('/go/'+IDS[0],result.html)
 def test_public_render_rejects_records_digest_and_provider_injection(self):
  for name,value in (("records",()),("selection_digest","x"),("provider",lambda:())):
   with self.subTest(name=name):
    with self.assertRaises(TypeError):candidate.render(as_of=NOW,**{name:value})

if __name__=='__main__':unittest.main()
