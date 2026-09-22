from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"scripts"))
import affiliate_cta_approved_context as approved
import affiliate_cta_pretransport_safety as subject
import affiliate_cta_kill_deadline_contract as kill_deadline

NOW=datetime(2026,9,22,4,0,tzinfo=timezone.utc)
IDS=tuple(f"itm_{number:024x}" for number in range(10))
CONTEXT=approved._make_test_context(IDS,lambda _value:None)
SOURCE="".join(f"{public_id}\tcontent-{index}\n" for index,public_id in enumerate(IDS)).encode("ascii")
ARTIFACT=b"artifact-fixture"

def build(**changes):
 values={"context":CONTEXT,"transport":lambda request:{"result":{"status":200,"items":[{"content_id":request._content_id,"affiliateURL":"https://al.dmm.co.jp/?lurl=https%3A%2F%2Fexample.invalid%2F"}]}},"clock":lambda:NOW,"monotonic_clock":lambda:0,"deadline":10,"source_bytes":SOURCE,"artifact_bytes":ARTIFACT,"expected_source_sha256":hashlib.sha256(SOURCE).hexdigest(),"expected_artifact_sha256":hashlib.sha256(ARTIFACT).hexdigest()}
 values.update(changes);return subject._build_fake_lifecycle_for_test(**values)

class PretransportSafetyTests(unittest.TestCase):
 def test_disabled_adapters_expose_no_values_or_transport(self):
  settings=subject.DisabledSettingsAdapter();transport=subject.DisabledTransport()
  self.assertEqual(settings.required_names(),subject.REQUIRED_SETTING_NAMES);self.assertIsNone(settings.read("anything"));self.assertIsNone(transport.request(object()))
  self.assertNotIn("anything",repr(settings));self.assertEqual(subject.kill_switch_state(True).status,subject.DISABLED)
  self.assertEqual(subject.kill_switch_state(False).status,subject.BLOCKED)
 def test_hash_mapping_context_failures_precede_transport(self):
  calls=[]
  cases=({"expected_source_sha256":"wrong"},{"expected_artifact_sha256":"wrong"},{"source_bytes":b"bad"},{"context":None})
  for changes in cases:
   with self.subTest(changes=changes):self.assertIsNone(build(transport=lambda request:calls.append(request),**changes))
  self.assertEqual(calls,[])
 def test_source_derives_mapping_and_external_mapping_is_not_an_api(self):
  lifecycle=build();self.assertEqual(len(lifecycle.records(lifecycle.context)),10)
  with self.assertRaises(TypeError):build(mapping={})
 def test_malformed_duplicate_trailing_and_mutation_fail_before_transport(self):
  calls=[]
  cases=(SOURCE[:-1],SOURCE+ b"x",SOURCE.replace(b"content-1",b"content-0"))
  for source in cases:
   with self.subTest(source=type(source)):
    expected=hashlib.sha256(bytes(source)).hexdigest()
    value=build(source_bytes=source,expected_source_sha256=expected,transport=lambda request:calls.append(request))
    self.assertIsNone(value)
  self.assertEqual(calls,[])
 def test_mutable_source_is_owned_before_later_mutation(self):
  source=bytearray(SOURCE);lifecycle=build(source_bytes=source,expected_source_sha256=hashlib.sha256(SOURCE).hexdigest())
  source[0]=ord("x")
  self.assertEqual(len(lifecycle.records(lifecycle.context)),10)
 def test_built_lifecycle_stops_after_revoke_or_deadline(self):
  lifecycle=build()
  lifecycle.revoke();self.assertIsNone(lifecycle.records(lifecycle.context))
  expired=build(monotonic_clock=lambda:10,deadline=10)
  self.assertIsNone(expired)
 def test_lifecycle_returns_one_shared_composition_and_timeout_stops(self):
  calls=[]
  def transport(request):
   calls.append(request)
   if len(calls)==4:raise TimeoutError()
   return {"result":{"status":200,"items":[{"content_id":request._content_id,"affiliateURL":"https://al.dmm.co.jp/?lurl=https%3A%2F%2Fexample.invalid%2F"}]}}
  lifecycle=build(transport=transport)
  self.assertIsNotNone(lifecycle);self.assertIsNone(lifecycle.records(lifecycle.context));self.assertEqual(len(calls),4)
 def test_success_is_sequential_bounded_and_receipts_are_sanitized(self):
  lifecycle=build();records=lifecycle.records(lifecycle.context)
  self.assertEqual(len(records),10);self.assertTrue(all(not value for value in (subject.SafetyReceipt(subject.BLOCKED,("X",)).transport_allowed,subject.SafetyReceipt(subject.BLOCKED,("X",)).settings_values_exposed,subject.SafetyReceipt(subject.BLOCKED,("X",)).production_write_performed)))
 def test_internal_builder_is_not_public_entry(self):
  with self.assertRaises(TypeError):subject.kill_switch_state(True,transport=object())

if __name__=='__main__':unittest.main()
