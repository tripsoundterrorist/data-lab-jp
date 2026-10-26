from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import revenue_mvp_fixed_scope_capture as subject
from revenue_mvp_lifecycle_receipt import public_item_id


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.temp = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.source = self.temp/'source.html'
        self.database = self.temp/'synthetic.db'
        self.environment = self.temp/'dummy.env'
        pairs = sorted((public_item_id('FANZA','digital','videoa',f'fixture-{i}'), f'fixture-{i}') for i in range(100))
        self.mapping = dict(pairs)
        body = ('<main>' + ''.join(
            f'<article class="item"><time>2020-01-01T00:00:00Z</time><a href="/go/{pid}">fixture</a></article>'
            for pid,_ in pairs) + '</main>').encode()
        self.source.write_bytes(body)
        self.database.write_bytes(b'fixture-not-a-real-database')
        self.environment.write_bytes(b'DUMMY_ONLY=1')
        self.bound = self.stack.enter_context(patch.object(subject.reader,'bound',return_value=True))
        self.resolve = self.stack.enter_context(patch.object(subject.reader.connector,'resolve_content_id',
            side_effect=lambda db,pid:self.mapping.get(pid)))
        self.fetch = self.stack.enter_context(patch.object(subject.reader,'fetch_exact',side_effect=self.response))
        self.stack.enter_context(patch.object(subject.reader.time,'sleep'))
        self.digest = sha256(body).hexdigest()
        self.dbhash = sha256(self.database.read_bytes()).hexdigest()
        self.key = b'synthetic-authentication-key-only-0000'

    @staticmethod
    def response(*,content_id,env_path):
        return {'result':{'status':200,'result_count':1,'total_count':1,'items':[
            {'content_id':content_id,'service_code':'digital','floor_code':'videoa',
             'affiliateURL':'https://al.fanza.co.jp/?lurl=https%3A%2F%2Fvideo.dmm.co.jp%2Fav%2F&af_id=fixture-990',
             'prices':{'price':'100~'},'imageURL':{'large':'https://pics.dmm.co.jp/fixture.jpg'}}]}}

    def capture(self,**changes):
        args = dict(expected_source_sha256=self.digest,expected_database_sha256=self.dbhash,
                    execute=True,confirmation=subject.confirmation_for(0),batch_index=0)
        args.update(changes)
        return subject.capture(self.source,self.database,self.environment,**args)

    def archive_args(self,**changes):
        args = dict(expected_database_sha256=self.dbhash,batch_index=0,
                    authentication_key=self.key,evaluated_at=datetime.now(timezone.utc))
        args.update(changes)
        return args

    def test_default_no_network(self):
        receipt,result=self.capture(execute=False)
        self.assertIsNone(result)
        self.fetch.assert_not_called()
        self.resolve.assert_not_called()

    def test_wrong_confirmation_and_boolean_batch(self):
        for changes in ({'confirmation':'wrong'},{'batch_index':True}):
            receipt,result=self.capture(**changes)
            self.assertIsNone(result)
        self.fetch.assert_not_called()

    def test_all_identity_resolution_precedes_network(self):
        self.resolve.side_effect=lambda db,pid:'wrong'
        receipt,result=self.capture()
        self.assertIsNone(result)
        self.fetch.assert_not_called()

    def test_source_or_database_drift_stops(self):
        self.bound.return_value=False
        receipt,result=self.capture()
        self.assertIsNone(result)
        self.fetch.assert_not_called()

    def test_success_exact_five_roundtrip(self):
        receipt,capture=self.capture()
        self.assertEqual(receipt['api_calls'],5)
        self.assertEqual(self.fetch.call_count,5)
        args=self.archive_args()
        data=subject.encode(capture,self.source.read_bytes(),**args)
        verified=subject.verify(data,self.source.read_bytes(),**args)
        self.assertEqual(verified['status'],'AUTHENTICATED_FORMAT_VERIFIED')
        self.assertFalse(verified['owned_capture_issued'])
        self.assertFalse(verified['publication_allowed'])
        self.assertNotIn(b'affiliateURL',data)
        self.assertNotIn(b'fixture-990',data)
        self.assertTrue(all(r['price_is_lower_bound'] for r in json.loads(data)['payload']['handoff']['records']))

    def test_midstream_failure_no_partial_capture_or_retry(self):
        seen=[]
        def fail(**kwargs):
            seen.append(1)
            if len(seen)==3:
                raise RuntimeError('synthetic failure')
            return self.response(**kwargs)
        self.fetch.side_effect=fail
        receipt,result=self.capture()
        self.assertIsNone(result)
        self.assertEqual(receipt['api_calls'],3)
        self.assertEqual(self.fetch.call_count,3)

    def test_zero_response_stops_as_separate_review(self):
        self.fetch.return_value={'result':{'status':200,'result_count':0,'total_count':0,'items':[]}}
        self.fetch.side_effect=None
        receipt,result=self.capture()
        self.assertIsNone(result)
        self.assertEqual(receipt['reason_code'],'NO_MATCH_REQUIRES_SEPARATE_REVIEW')
        self.assertEqual(self.fetch.call_count,1)

    def test_forged_capture_cannot_encode(self):
        _,capture=self.capture()
        forged=subject.Capture(5,capture._data)
        with self.assertRaisesRegex(ValueError,'OWNED_CAPTURE_REQUIRED'):
            subject.encode(forged,self.source.read_bytes(),**self.archive_args())

    def test_tampered_wrong_key_scope_database_source_and_expiry(self):
        _,capture=self.capture()
        args=self.archive_args()
        data=subject.encode(capture,self.source.read_bytes(),**args)
        for changes in ({'authentication_key':b'x'*32},{'batch_index':1},
                        {'expected_database_sha256':'0'*64},
                        {'evaluated_at':datetime.now(timezone.utc)+timedelta(hours=25)}):
            modified=dict(args,**changes)
            self.assertEqual(subject.verify(data,self.source.read_bytes(),**modified)['status'],'BLOCKED')
        modified=data.replace(b'"price":100',b'"price":101',1)
        self.assertEqual(subject.verify(modified,self.source.read_bytes(),**args)['status'],'BLOCKED')
        self.assertEqual(subject.verify(data,self.source.read_bytes()+b' ',**args)['status'],'BLOCKED')

    def test_duplicate_fields_and_legacy_format_refused(self):
        args=self.archive_args()
        for data in (b'{"payload":{},"payload":{},"authentication":"x"}',
                     b'{"payload":{"version":"1"},"authentication":"x"}',b'x'* (subject.MAX_BYTES+1)):
            self.assertEqual(subject.verify(data,self.source.read_bytes(),**args)['status'],'BLOCKED')

    def test_no_files_changed(self):
        before={p.name:p.read_bytes() for p in self.temp.iterdir()}
        _,capture=self.capture()
        subject.encode(capture,self.source.read_bytes(),**self.archive_args())
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.temp.iterdir()})

    def test_result_rate_limit_stops_without_evidence(self):
        self.fetch.side_effect=None
        self.fetch.return_value={'result':{'status':429}}
        receipt,result=self.capture()
        self.assertIsNone(result)
        self.assertEqual(receipt['reason_code'],'STOP_RATE_LIMIT')
        self.assertEqual(self.fetch.call_count,1)

    def test_valid_signature_does_not_bypass_record_validation(self):
        import hmac
        _,capture=self.capture()
        args=self.archive_args()
        data=subject.encode(capture,self.source.read_bytes(),**args)
        for field,value in (('price',True),('price',-1),('image_url','https://evil.test/x'),
                            ('price_is_lower_bound',1)):
            envelope=json.loads(data)
            envelope['payload']['handoff']['records'][0][field]=value
            envelope['authentication']=hmac.new(self.key,subject.DOMAIN+subject._json(envelope['payload']),'sha256').hexdigest()
            self.assertEqual(subject.verify(subject._json(envelope),self.source.read_bytes(),**args)['status'],'BLOCKED')


if __name__=='__main__':
    unittest.main()
