from dataclasses import replace
from datetime import datetime,timezone,timedelta
from hashlib import sha256
from unittest.mock import patch
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import revenue_mvp_fixed_scope_acquisition_evidence as subject
from tests.test_revenue_mvp_fixed_scope_first_five import FirstFiveTests


class AcquisitionEvidenceTests(FirstFiveTests):
    def setUp(self):
        super().setUp()
        self.candidate=self.source.read_bytes()+b'fixture display delta'
        for name,value in (("BASELINE",self.source_hash),
                           ("CANDIDATE",sha256(self.candidate).hexdigest())):
            mock=patch.object(subject.display,name,value)
            mock.start(); self.addCleanup(mock.stop)

    def capture(self,**kwargs):
        options=dict(expected_source_sha256=self.source_hash,
                     expected_database_sha256=self.db_hash,
                     execute=True,confirmation=subject.CONFIRMATION)
        options.update(kwargs)
        with patch.object(subject.reader.connector,"resolve_content_id",side_effect=lambda db,x:self.mapping[x]), \
             patch.object(subject.reader,"fetch_exact",side_effect=self.fetch), \
             patch.object(subject.reader.time,"sleep",side_effect=self.waits.append):
            return subject.capture(self.source,self.db,self.env,self.candidate,**options)

    def test_complete_mock_capture_is_owned_and_sanitized(self):
        evidence=self.capture()
        self.assertTrue(subject.review(evidence,self.source.read_bytes(),self.candidate))
        self.assertEqual(evidence.api_calls,100)
        self.assertEqual(len(self.calls),100)
        self.assertEqual(len(set(self.calls)),100)
        self.assertEqual(self.waits,[1.0]*99)
        for private in ('fixture-', 'https://', 'itm_'):
            self.assertNotIn(private,str(evidence.summary()))
            self.assertNotIn(private,repr(evidence))
        self.assertEqual(subject.reader.digest(self.db),self.db_hash)

    def test_offline_and_missing_approval_make_no_requests(self):
        self.assertEqual(self.capture(execute=False).api_calls,0)
        self.assertEqual(self.capture(confirmation=None).api_calls,0)
        self.assertFalse(self.calls)

    def test_manual_json_and_cloned_dataclass_are_not_owned(self):
        evidence=self.capture()
        for fake in (evidence.summary(),replace(evidence)):
            self.assertFalse(subject.review(fake,self.source.read_bytes(),self.candidate))

    def test_future_stale_and_changed_scope_fail_review(self):
        evidence=self.capture()
        for stamp in (datetime.now(timezone.utc)+timedelta(hours=25),
                      datetime.now(timezone.utc)-timedelta(hours=1)):
            self.assertFalse(subject.review(evidence,self.source.read_bytes(),self.candidate,evaluated_at=stamp))
        self.assertFalse(subject.review(evidence,self.source.read_bytes()+b'other',self.candidate))
        self.assertFalse(subject.review(evidence,self.source.read_bytes(),b'other'))

    def test_capture_rate_limit_stops_without_receipt_or_retry(self):
        with patch.object(self,"fetch",return_value={'result':{'status':429}}):
            evidence=self.capture()
        self.assertEqual(evidence.api_calls,1)
        self.assertFalse(subject.review(evidence,self.source.read_bytes(),self.candidate))
        self.assertEqual(evidence.summary()['validated_count'],0)

    def test_all_identities_resolved_before_requests(self):
        self.mapping.clear()
        evidence=self.capture()
        self.assertEqual(evidence.api_calls,0)
        self.assertFalse(self.calls)
