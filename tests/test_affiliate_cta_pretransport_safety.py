from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"scripts"))
import affiliate_cta_approved_context as approved
import affiliate_cta_pretransport_safety as subject

NOW=datetime(2026,9,22,4,0,tzinfo=timezone.utc)
IDS=tuple(f"itm_{number:024x}" for number in range(10))
CONTEXT=approved._make_test_context(IDS,lambda _value:None)
SOURCE=b"source-fixture";ARTIFACT=b"artifact-fixture"

def mapping():return {public_id:"content-"+str(index) for index,public_id in enumerate(IDS)}
def build(**changes):
 values={"context":CONTEXT,"mapping":mapping(),"transport":lambda request:{"result":{"status":200,"items":[{"content_id":request._content_id,"affiliateURL":"https://al.dmm.co.jp/?lurl=https%3A%2F%2Fexample.invalid%2F"}]}},"clock":lambda:NOW,"source_bytes":SOURCE,"artifact_bytes":ARTIFACT,"expected_source_sha256":hashlib.sha256(SOURCE).hexdigest(),"expected_artifact_sha256":hashlib.sha256(ARTIFACT).hexdigest()}
 values.update(changes);return subject._build_fake_lifecycle_for_test(**values)

class PretransportSafetyTests(unittest.TestCase):
 def test_disabled_adapters_expose_no_values_or_transport(self):
  settings=subject.DisabledSettingsAdapter();transport=subject.DisabledTransport()
  self.assertEqual(settings.required_names(),subject.REQUIRED_SETTING_NAMES);self.assertIsNone(settings.read("anything"));self.assertIsNone(transport.request(object()))
  self.assertNotIn("anything",repr(settings));self.assertEqual(subject.kill_switch_state(True).status,subject.DISABLED)
  self.assertEqual(subject.kill_switch_state(False).status,subject.BLOCKED)
 def test_hash_mapping_context_failures_precede_transport(self):
  calls=[]
  cases=({"expected_source_sha256":"wrong"},{"expected_artifact_sha256":"wrong"},{"mapping":{}},{"context":None})
  for changes in cases:
   with self.subTest(changes=changes):self.assertIsNone(build(transport=lambda request:calls.append(request),**changes))
  self.assertEqual(calls,[])
 def test_lifecycle_returns_one_shared_composition_and_timeout_stops(self):
  calls=[]
  def transport(request):
   calls.append(request)
   if len(calls)==4:raise TimeoutError()
   return {"result":{"status":200,"items":[{"content_id":request._content_id,"affiliateURL":"https://al.dmm.co.jp/?lurl=https%3A%2F%2Fexample.invalid%2F"}]}}
  lifecycle=build(transport=transport)
  self.assertIsNotNone(lifecycle);self.assertIsNone(lifecycle.records(CONTEXT));self.assertEqual(len(calls),4)
 def test_success_is_sequential_bounded_and_receipts_are_sanitized(self):
  lifecycle=build();records=lifecycle.records(CONTEXT)
  self.assertEqual(len(records),10);self.assertTrue(all(not value for value in (subject.SafetyReceipt(subject.BLOCKED,("X",)).transport_allowed,subject.SafetyReceipt(subject.BLOCKED,("X",)).settings_values_exposed,subject.SafetyReceipt(subject.BLOCKED,("X",)).production_write_performed)))
 def test_internal_builder_is_not_public_entry(self):
  with self.assertRaises(TypeError):subject.kill_switch_state(True,transport=object())

if __name__=='__main__':unittest.main()
