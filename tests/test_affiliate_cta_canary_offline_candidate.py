from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys, unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"scripts"))
import affiliate_cta_canary_offline_candidate as candidate
NOW=datetime(2026,9,22,4,0,tzinfo=timezone.utc)
ID="itm_0123456789abcdef01234567"
class CandidateTests(unittest.TestCase):
 def test_fresh_fixture_has_fixed_cta_and_proximate_disclosure_only(self):
  r=candidate.render(({"public_id":ID,"title":"fixture","observed_at":NOW,"fresh":True,"revalidation_status":"API_VISIBLE_AFFILIATE_PRESENT"},),selection_digest=candidate.SELECTION_DIGEST,as_of=NOW)
  self.assertIn('/go/'+ID,r.html);self.assertIn('公式商品ページを見る（外部サイト）',r.html);self.assertEqual(r.cta_count,1);self.assertFalse(r.cta_activation_allowed)
 def test_stale_or_error_hides_cta(self):
  for status,time in (("API_ERROR",NOW),("API_VISIBLE_AFFILIATE_PRESENT",NOW-timedelta(minutes=16))):
   r=candidate.render(({"public_id":ID,"title":"fixture","observed_at":time,"fresh":True,"revalidation_status":status},),selection_digest=candidate.SELECTION_DIGEST,as_of=NOW);self.assertEqual(r.cta_count,0)
 def test_invalid_contracts_fail_closed_and_escape_title(self):
  base={"public_id":ID,"title":"<script>x</script>","observed_at":NOW,"fresh":True,"revalidation_status":"API_VISIBLE_AFFILIATE_PRESENT"}
  for value in ("wrong",):
   with self.assertRaises(ValueError): candidate.render((base,),selection_digest=value,as_of=NOW)
  with self.assertRaises(ValueError): candidate.render(tuple(base for _ in range(11)),selection_digest=candidate.SELECTION_DIGEST,as_of=NOW)
  for key,value in (("public_id",None),("title",None),("revalidation_status",None),("observed_at","bad"),("fresh","yes")):
   bad=dict(base);bad[key]=value
   with self.assertRaises(ValueError): candidate.render((bad,),selection_digest=candidate.SELECTION_DIGEST,as_of=NOW)
  r=candidate.render((base,),selection_digest=candidate.SELECTION_DIGEST,as_of=NOW)
  self.assertIn("&lt;script&gt;",r.html);self.assertNotIn("<script>x",r.html)
  self.assertLess(r.html.index("PR："),r.html.index("公式商品ページ"))
  self.assertTrue(all(value is False for value in (r.publication_allowed,r.affiliate_eligibility_allowed,r.gate_mutation_allowed,r.cta_activation_allowed)))
if __name__=='__main__': unittest.main()
