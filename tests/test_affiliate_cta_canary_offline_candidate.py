from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import affiliate_cta_canary_offline_candidate as candidate

NOW=datetime(2026,9,22,4,0,tzinfo=timezone.utc)
ID="itm_000000000000000000000000"
RECORD={"public_id":ID,"title":"fixture","observed_at":NOW,"fresh":True,"revalidation_status":"API_VISIBLE_AFFILIATE_PRESENT"}


class CandidateTests(unittest.TestCase):
 def test_render_fails_closed_without_protected_approved_context(self):
  with self.assertRaisesRegex(ValueError,"APPROVED_CONTEXT_UNAVAILABLE"):
   candidate.render((RECORD,),as_of=NOW)
 def test_caller_digest_or_selection_control_is_not_an_api_surface(self):
  for name,value in (("selection_digest","x"),("selected_public_ids",(ID,))):
   with self.subTest(name=name):
    with self.assertRaises(TypeError): candidate.render((RECORD,),as_of=NOW,**{name:value})

if __name__=='__main__': unittest.main()
