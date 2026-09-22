from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"scripts"))
import affiliate_cta_kill_deadline_contract as subject

class KillDeadlineTests(unittest.TestCase):
 def test_default_is_blocked_and_token_is_redacted(self):
  self.assertEqual(subject.default_state(),subject.BLOCKED);self.assertEqual(repr(subject._new_test_token()),"<KillToken>")
 def test_revoke_is_idempotent_and_blocks_before_transport(self):
  token=subject._new_test_token();token.revoke();token.revoke();calls=[]
  guarded=subject._guarded_transport_for_test(token,lambda:0,10,lambda request:calls.append(request))
  self.assertIsNone(guarded(object()));self.assertEqual(calls,[])
 def test_deadline_before_and_after_return_blocks_no_retry(self):
  token=subject._new_test_token();calls=[]
  self.assertIsNone(subject._guarded_transport_for_test(token,lambda:10,10,lambda request:calls.append(request))(object()));self.assertEqual(calls,[])
  ticks=iter((0,10));guarded=subject._guarded_transport_for_test(token,lambda:next(ticks),10,lambda request:calls.append(request) or {})
  self.assertIsNone(guarded(object()));self.assertEqual(len(calls),1)
 def test_middle_revoke_stops_later_calls(self):
  token=subject._new_test_token();calls=[]
  def transport(request):
   calls.append(request)
   if len(calls)==1:token.revoke()
   return {}
  guarded=subject._guarded_transport_for_test(token,lambda:0,10,transport)
  self.assertIsNone(guarded(object()));self.assertIsNone(guarded(object()));self.assertEqual(len(calls),1)
 def test_public_inputs_are_not_accepted(self):
  with self.assertRaises(TypeError):subject.default_state(token=object())

if __name__=='__main__':unittest.main()
