from contextlib import ExitStack
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import revenue_mvp_fixed_scope_private_save as subject
from revenue_mvp_lifecycle_receipt import public_item_id


class PrivateSaveTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack(); self.addCleanup(self.stack.close)
        self.root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.output=self.root/('fixed-five-b00-'+'a'*32+'.json')
        self.stack.enter_context(patch.object(subject,'EVIDENCE_DIRECTORY',self.root))
        self.acl=self.stack.enter_context(patch.object(subject.protected,'_acl_safe',return_value=True))
        self.key_reader=self.stack.enter_context(patch.object(subject.protected,'read_protected_key',side_effect=AssertionError('NO_REAL_KEY')))
        pairs=sorted((public_item_id('FANZA','digital','videoa',f'fixture-{i}'),f'fixture-{i}') for i in range(100))
        self.source=('<main>'+''.join(f'<article class="item"><time>2020-01-01T00:00:00Z</time><a href="/go/{pid}">fixture</a></article>' for pid,_ in pairs)+'</main>').encode()
        source_path=self.root/'source.html'; source_path.write_bytes(self.source)
        database=self.root/'fixture.db'; database.write_bytes(b'fixture')
        environment=self.root/'dummy.env'; environment.write_bytes(b'DUMMY_ONLY=1')
        reader=subject.capture_format.reader
        mapping=dict(pairs)
        def response(**kwargs):
            return {'result':{'status':200,'result_count':1,'total_count':1,'items':[
                {'content_id':kwargs['content_id'],'service_code':'digital','floor_code':'videoa',
                 'affiliateURL':'https://al.fanza.co.jp/?lurl=https%3A%2F%2Fvideo.dmm.co.jp%2Fav%2F&af_id=fixture-990',
                 'prices':{'price':'100~'},'imageURL':{'large':'https://pics.dmm.co.jp/fixture.jpg'}}]}}
        with patch.object(reader,'bound',return_value=True),patch.object(reader.connector,'resolve_content_id',side_effect=lambda db,pid:mapping[pid]),patch.object(reader,'fetch_exact',side_effect=response),patch.object(reader.time,'sleep'):
            receipt,self.evidence=subject.capture_format.capture(source_path,database,environment,
                expected_source_sha256=sha256(self.source).hexdigest(),expected_database_sha256='a'*64,
                execute=True,confirmation=subject.capture_format.confirmation_for(0))
        self.assertIsNotNone(self.evidence)
        self.key=b'synthetic-key-only-for-save-tests-0000'

    def save(self,**changes):
        args=dict(expected_database_sha256='a'*64,batch_index=0,
            authentication_key=self.key,evaluated_at=datetime.now(timezone.utc),confirmation=subject.CONFIRMATION)
        args.update(changes)
        return subject.save(self.evidence,self.source,self.output,**args)

    def test_default_no_write_or_acl_or_key_read(self):
        self.acl.reset_mock()
        result=self.save(confirmation=None)
        self.assertFalse(result['write_attempted'])
        self.assertFalse(self.output.exists())
        self.acl.assert_not_called(); self.key_reader.assert_not_called()

    def test_success_readback_and_no_key_read(self):
        result=self.save()
        self.assertEqual(result['status'],'PRIVATE_FIXED_FIVE_ARCHIVE_SAVED')
        self.assertEqual(result['archive_sha256'],sha256(self.output.read_bytes()).hexdigest())
        self.assertFalse(result['publication_allowed'])
        self.key_reader.assert_not_called()

    def test_existing_file_never_overwritten(self):
        self.output.write_bytes(b'KEEP')
        result=self.save()
        self.assertEqual(result['reason_code'],'EXISTING_OUTPUT_REFUSED')
        self.assertEqual(self.output.read_bytes(),b'KEEP')

    def test_acl_fail_stops_before_encoding(self):
        self.acl.return_value=False
        with patch.object(subject.capture_format,'encode') as encode:
            result=self.save()
            encode.assert_not_called()
        self.assertFalse(result['write_attempted'])

    def test_unowned_capture_never_creates_file(self):
        self.evidence=subject.capture_format.Capture(5,self.evidence._data)
        result=self.save()
        self.assertFalse(result['write_attempted'])
        self.assertFalse(self.output.exists())

    def test_wrong_path_and_batch_do_not_write(self):
        self.output=self.root/'not-approved.json'
        self.assertFalse(self.save()['write_attempted'])
        self.output=self.root/('fixed-five-b00-'+'a'*32+'.json')
        self.assertFalse(self.save(batch_index=1)['write_attempted'])

    def test_readback_failure_retains_file_and_requires_review(self):
        with patch.object(subject,'_read_back',return_value=b'WRONG'):
            result=self.save()
        self.assertEqual(result['status'],'BLOCKED')
        self.assertFalse(result['output_written'])
        self.assertTrue(result['partial_file_may_exist'])
        self.assertTrue(result['manual_review_required'])
        self.assertTrue(self.output.exists())

    def test_flush_failure_retains_file_no_retry(self):
        with patch.object(subject.os,'fsync',side_effect=OSError('synthetic failure')) as sync:
            result=self.save()
        self.assertTrue(result['manual_review_required'])
        self.assertEqual(sync.call_count,1)
        before=self.output.read_bytes()
        self.assertEqual(self.save()['reason_code'],'EXISTING_OUTPUT_REFUSED')
        self.assertEqual(self.output.read_bytes(),before)

    def test_acl_change_after_create_blocks_success(self):
        self.acl.side_effect=[True,True,False]
        result=self.save()
        self.assertFalse(result['output_written'])
        self.assertTrue(result['manual_review_required'])

    def test_acl_change_before_create_stops(self):
        self.acl.side_effect=[True,False]
        result=self.save()
        self.assertFalse(result['write_attempted'])
        self.assertFalse(self.output.exists())

    def test_windows_reparse_point_refused_before_write(self):
        from types import SimpleNamespace
        with patch.object(Path,'is_symlink',return_value=False),patch.object(Path,'lstat',return_value=SimpleNamespace(st_file_attributes=0x400)):
            result=self.save()
        self.assertFalse(result['write_attempted'])
        self.assertFalse(self.output.exists())

    def test_wrong_key_type_and_source_binding_no_write(self):
        result=self.save(authentication_key=b'short')
        self.assertFalse(result['write_attempted'])
        result=subject.save(self.evidence,self.source+b' ',self.output,
            expected_database_sha256='a'*64,batch_index=0,authentication_key=self.key,
            evaluated_at=datetime.now(timezone.utc),confirmation=subject.CONFIRMATION)
        self.assertFalse(result['write_attempted'])
        self.assertFalse(self.output.exists())


if __name__=='__main__':
    unittest.main()
