from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

import affiliate_cta_canary_plan as plan_module
import affiliate_cta_canonical_selection_preflight as subject
import affiliate_cta_exact_selection as exact

NOW=datetime(2026,9,22,7,0,tzinfo=timezone.utc)
ID="itm_0123456789abcdef01234567"


def plan():
    return plan_module.current_plan()


def payload(content_id):
    return {"expected_content_id":content_id,"observed_at":NOW,"call_status":"success","error_class":None,"source_status_code":200,"result_count":1,"items":[{"content_id":content_id,"affiliate_link_present":True}]}


class CanonicalSelectionPreflightTests(unittest.TestCase):
    def test_default_path_is_blocked_without_callbacks(self):
        result=subject.run((),as_of=None,execution_authorized=False,one_shot=False,source_database_sha256=None,live_artifact_sha256=None,resolve_content_id=None,fetch_sanitized_item_payload=None,plan=None)
        self.assertEqual(result.status,subject.BLOCKED)
        self.assertEqual(result.api_request_attempt_count,0)
        self.assertFalse(result.cta_activation_allowed)

    def test_ready_receipt_contains_only_digest_hashes_and_counts(self):
        result=subject.run((ID,),as_of=NOW,execution_authorized=True,one_shot=True,source_database_sha256="a"*64,live_artifact_sha256="b"*64,resolve_content_id=lambda _id:"content1",fetch_sanitized_item_payload=payload,plan=plan())
        self.assertEqual(result.status,subject.READY)
        self.assertEqual(result.selection_digest,exact.canonical_digest((ID,)))
        self.assertEqual(result.api_request_attempt_count,1)
        serialized=str(result.to_dict())
        self.assertNotIn(ID,serialized)
        self.assertNotIn("content1",serialized)
        self.assertNotIn("al.dmm",serialized)
        self.assertTrue(all(not value for value in (result.identifiers_exposed,result.affiliate_urls_exposed,result.production_write_performed,result.cta_activation_allowed,result.d1_write_allowed,result.deployment_allowed)))

    def test_failed_preflight_never_emits_digest(self):
        result=subject.run((ID,),as_of=NOW,execution_authorized=True,one_shot=True,source_database_sha256="a"*64,live_artifact_sha256="b"*64,resolve_content_id=lambda _id:None,fetch_sanitized_item_payload=payload,plan=plan())
        self.assertEqual(result.status,subject.BLOCKED)
        self.assertIsNone(result.selection_digest)


if __name__=="__main__": unittest.main()
