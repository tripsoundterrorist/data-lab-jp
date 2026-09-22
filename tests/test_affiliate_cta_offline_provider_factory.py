from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"scripts"))
import affiliate_cta_approved_context as approved
import affiliate_cta_canary_offline_candidate as render
import affiliate_cta_click_revalidation_candidate as click
import affiliate_cta_offline_provider_factory as factory

NOW=datetime(2026,9,22,4,0,tzinfo=timezone.utc)
IDS=tuple(f"itm_{number:024x}" for number in range(10))
CONTEXT=approved._make_test_context(IDS,lambda _value:None)
DIGEST=approved.exact.canonical_digest(IDS)

def mapping():return {public_id:"content-"+str(index) for index,public_id in enumerate(IDS)}
def payload(content_id,target="https://al.dmm.co.jp/?lurl=https%3A%2F%2Fexample.invalid%2F"):
 return {"result":{"status":200,"items":[{"content_id":content_id,"affiliateURL":target}]}}
def build(fetcher=None, clock=lambda:NOW, value=None):
 return factory._build_offline_provider_for_test(value or CONTEXT,mapping(),fetcher or payload,clock)

class OfflineProviderFactoryTests(unittest.TestCase):
 def test_exact_ten_are_sequential_once_and_shared_by_click_and_render(self):
  calls=[]
  def fetch(content):calls.append(content);return payload(content)
  provider=build(fetch)
  records=provider.records(CONTEXT)
  self.assertEqual(len(records),10);self.assertEqual(len(calls),10);self.assertEqual(len(set(calls)),10)
  with mock.patch.object(approved,"production_context",return_value=CONTEXT),mock.patch.object(approved,"production_observe",provider.observe),mock.patch.object(approved,"production_render_records",provider.records):
   self.assertEqual(click.decide(version=click.VERSION,clicked_public_id=IDS[0],evaluated_at=NOW).status,click.ALLOWED)
   self.assertEqual(render.render(as_of=NOW).cta_count,10)
  self.assertEqual(len(calls),21)
 def test_mapping_missing_or_duplicate_rejected_before_fetch(self):
  bad=mapping();bad.pop(IDS[0])
  with self.assertRaises(ValueError):factory._build_offline_provider_for_test(CONTEXT,bad,payload,lambda:NOW)
  bad=mapping();bad[IDS[1]]=bad[IDS[0]]
  with self.assertRaises(ValueError):factory._build_offline_provider_for_test(CONTEXT,bad,payload,lambda:NOW)
 def test_error_rate_limit_match_target_and_clock_fail_closed(self):
  cases=(lambda content:(_ for _ in ()).throw(RuntimeError()),lambda content:{"result":{"status":429,"items":[]}},lambda content:{"result":{"status":200,"items":[]}},lambda content:{"result":{"status":200,"items":[{"content_id":content,"affiliateURL":"https://evil.invalid/"}]}},lambda content:{"result":{"status":200,"items":[{"content_id":content,"affiliateURL":"https://al.dmm.co.jp/x"},{"content_id":content,"affiliateURL":"https://al.dmm.co.jp/x"}]}})
  for fetcher in cases:
   with self.subTest(fetcher=fetcher):self.assertIsNone(build(fetcher).observe(IDS[0]))
  self.assertIsNone(build(clock=lambda:None).observe(IDS[0]))
 def test_snapshot_is_owned_and_fetcher_time_is_ignored(self):
  raw=payload(mapping()[IDS[0]]);raw["checked_at"]="caller"
  provider=build(lambda _content:raw)
  observation=provider.observe(IDS[0]);raw["result"]["items"][0]["content_id"]="changed"
  self.assertEqual(observation.checked_at,NOW);self.assertEqual(observation.response["result"]["items"][0]["content_id"],mapping()[IDS[0]])
  with self.assertRaises(TypeError):observation.response["x"]=1
 def test_outside_and_public_injection_do_not_reach_factory(self):
  provider=build();self.assertIsNone(provider.observe("itm_00000000000000000000000a"))
  with self.assertRaises(TypeError):click.decide(version=click.VERSION,clicked_public_id=IDS[0],evaluated_at=NOW,fetcher=payload)
  with self.assertRaises(TypeError):render.render(as_of=NOW,provider=provider)

if __name__=='__main__':unittest.main()
