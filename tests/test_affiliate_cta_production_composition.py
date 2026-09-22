from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"scripts"))
import affiliate_cta_approved_context as approved
import affiliate_cta_canary_offline_candidate as render
import affiliate_cta_click_revalidation_candidate as click
import affiliate_cta_production_composition as composition

NOW=datetime(2026,9,22,4,0,tzinfo=timezone.utc)
IDS=tuple(f"itm_{number:024x}" for number in range(10))
CONTEXT=approved._make_test_context(IDS,lambda _value:None)

def mapping():return {public_id:"content-"+str(index) for index,public_id in enumerate(IDS)}
def payload(content):return {"result":{"status":200,"items":[{"content_id":content,"affiliateURL":"https://al.dmm.co.jp/?lurl=https%3A%2F%2Fexample.invalid%2F"}]}}
def build(transport=None):
 return composition._build_offline_composition_for_test(CONTEXT,mapping(),transport or (lambda request:payload(request._content_id)),lambda:NOW)

class ProductionCompositionTests(unittest.TestCase):
 def test_default_kill_switch_is_disabled_and_public_paths_block(self):
  self.assertTrue(composition.KILL_SWITCH_DISABLED);self.assertIsNone(composition.production_provider())
  self.assertEqual(click.decide(version=click.VERSION,clicked_public_id=IDS[0],evaluated_at=NOW).status,click.BLOCKED)
  with self.assertRaises(ValueError):render.render(as_of=NOW)
 def test_fake_transport_exact_ten_opaque_sequential_and_no_retry(self):
  calls=[]
  def transport(request):
   calls.append(request);self.assertEqual(repr(request),"<OpaqueProviderRequest>");return payload(request._content_id)
  lifecycle=build(transport);result=lifecycle.records(lifecycle.context)
  self.assertEqual(len(result),10);self.assertEqual(len(calls),10);self.assertEqual(len({id(value) for value in calls}),10)
 def test_mapping_or_context_failure_has_zero_transport_calls(self):
  calls=[];bad=mapping();bad.pop(IDS[0])
  with self.assertRaises(ValueError):composition._build_offline_composition_for_test(CONTEXT,bad,lambda request:calls.append(request),lambda:NOW)
  with self.assertRaises(ValueError):composition._build_offline_composition_for_test(None,mapping(),lambda request:calls.append(request),lambda:NOW)
  self.assertEqual(calls,[])
 def test_transport_first_and_middle_fail_stop_without_retry(self):
  for stop_at in (0,4):
   with self.subTest(stop_at=stop_at):
    calls=[]
    def transport(request):
     calls.append(request)
     if len(calls)-1==stop_at:raise TimeoutError()
     return payload(request._content_id)
    lifecycle=build(transport);self.assertIsNone(lifecycle.records(lifecycle.context));self.assertEqual(len(calls),stop_at+1)
 def test_click_and_render_share_composition_provider(self):
  value=build()
  with mock.patch.object(composition,"production_provider",return_value=value),mock.patch.object(approved,"production_context",return_value=CONTEXT):
   self.assertEqual(click.decide(version=click.VERSION,clicked_public_id=IDS[0],evaluated_at=NOW).status,click.ALLOWED)
   result=render.render(as_of=NOW)
  self.assertEqual(result.cta_count,10);self.assertFalse(result.cta_activation_allowed)
 def test_public_injection_rejected(self):
  with self.assertRaises(TypeError):click.decide(version=click.VERSION,clicked_public_id=IDS[0],evaluated_at=NOW,transport=lambda:None)
  with self.assertRaises(TypeError):render.render(as_of=NOW,mapping=mapping())

if __name__=='__main__':unittest.main()
