from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from unittest.mock import patch
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import revenue_mvp_price_display_transition as subject


class Response:
    status=200
    def __init__(self,body,url=subject.URL):
        self.body,self.url=body,url
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def geturl(self): return self.url
    def read(self,size): return self.body[:size]


class PriceDisplayTransitionTests(unittest.TestCase):
    def setUp(self):
        self.old=('<article><p class="price">1,000円</p></article>\n'*100).encode()
        self.new=self.old.replace('円</p>'.encode(),'円〜</p>'.encode())
        self.old_hash=sha256(self.old).hexdigest()
        self.new_hash=sha256(self.new).hexdigest()
        self.p1=patch.object(subject,"BASELINE",self.old_hash)
        self.p2=patch.object(subject,"CANDIDATE",self.new_hash)
        self.p1.start(); self.p2.start()
        self.addCleanup(self.p1.stop); self.addCleanup(self.p2.stop)
        self.history={"items_artifact_sha256":self.old_hash,"status":"historical_fixture"}
        self.original=copy.deepcopy(self.history)

    def capture(self,body):
        with patch.object(subject.urllib.request,"urlopen",return_value=Response(body)):
            return subject.capture_public_page()

    def review(self,**kwargs):
        return subject.review(self.old,self.new,self.history,**kwargs)

    def test_unpublished_candidate_does_not_renew_historical_verification(self):
        result=self.review()
        self.assertEqual(result.status,"CANDIDATE_PENDING_LIVE_DISPLAY_VERIFICATION")
        self.assertFalse(result.current_display_match_observed)
        self.assertEqual(self.history,self.original)

    def test_actual_candidate_capture_matches_only_display(self):
        result=self.review(observation=self.capture(self.new))
        self.assertEqual(result.status,"LIVE_DISPLAY_MATCH_OBSERVED")
        self.assertTrue(result.current_display_match_observed)
        for field in ("publication_allowed","gate_mutation_allowed","database_write_performed"):
            self.assertFalse(getattr(result,field))
        self.assertEqual(self.history,self.original)

    def test_baseline_capture_is_not_candidate_live_proof(self):
        result=self.review(observation=self.capture(self.old))
        self.assertEqual(result.status,"CANDIDATE_NOT_YET_PUBLIC")
        self.assertFalse(result.current_display_match_observed)

    def test_unrelated_public_page_or_candidate_change_blocks(self):
        self.assertEqual(self.review(observation=self.capture(b"other")).status,"BLOCKED")
        self.assertEqual(subject.review(self.old,self.new+b"other",self.history).status,"BLOCKED")

    def test_forged_receipt_or_capture_blocks(self):
        self.assertEqual(self.review(observation={"verified":True,"digest":self.new_hash}).status,"BLOCKED")
        forged=subject._PageObservation(self.new_hash,datetime.now(timezone.utc),object())
        self.assertEqual(self.review(observation=forged).status,"BLOCKED")

    def test_historical_digest_cannot_be_relabelled_as_candidate(self):
        history={"items_artifact_sha256":self.new_hash}
        self.assertEqual(subject.review(self.old,self.new,history).status,"BLOCKED")

    def test_stale_future_or_naive_capture_blocks(self):
        observed=self.capture(self.new)
        now=datetime.now(timezone.utc)
        for stamp in (now-timedelta(minutes=16),now+timedelta(minutes=1),now.replace(tzinfo=None)):
            self.assertEqual(self.review(observation=replace(observed,observed_at=stamp),
                                       evaluated_at=now).status,"BLOCKED")

    def test_redirect_or_bad_http_capture_refused(self):
        for response in (Response(self.new,"https://other.invalid/"),Response(self.new)):
            if response.url==subject.URL: response.status=201
            with patch.object(subject.urllib.request,"urlopen",return_value=response):
                with self.assertRaises(ValueError): subject.capture_public_page()

    def test_large_capture_refused(self):
        with patch.object(subject.urllib.request,"urlopen",
                          return_value=Response(b"x"*(subject.MAX_BYTES+1))):
            with self.assertRaises(ValueError): subject.capture_public_page()

    def test_windows_eol_is_normalized(self):
        observed=self.capture(self.new.replace(b"\n",b"\r\n"))
        self.assertEqual(self.review(observation=observed).status,"LIVE_DISPLAY_MATCH_OBSERVED")


if __name__=="__main__":
    unittest.main()
