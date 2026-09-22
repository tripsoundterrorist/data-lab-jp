import json,re
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/"runtime/evidence/affiliate-cta-canonical-preflight-20260922.json"
class EvidenceTests(unittest.TestCase):
 def test_sanitized_exact_receipt_remains_nonactivating(self):
  value=json.loads(PATH.read_text(encoding="utf-8"));self.assertEqual(value["status"],"CANONICAL_SELECTION_READY_FOR_EXACT_REVIEW")
  self.assertEqual(value["submitted_count"],10);self.assertEqual(value["api_request_attempt_count"],10);self.assertEqual(value["selected_count"],10)
  self.assertRegex(value["selection_digest"],r"[0-9a-f]{64}")
  for key in ("identifiers_exposed","affiliate_urls_exposed","secret_values_exposed","production_write_performed","cta_activation_allowed","d1_write_allowed","deployment_allowed"): self.assertIs(value[key],False,key)
  text=PATH.read_text(encoding="utf-8");self.assertNotRegex(text,r"itm_[0-9a-f]{24}|https?://|affiliateURL|DMM_API_ID|DMM_AFFILIATE_ID")
if __name__=="__main__":unittest.main()
