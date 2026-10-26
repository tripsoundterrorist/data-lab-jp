from datetime import datetime, timezone
from hashlib import sha256
import hmac
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import revenue_mvp_fixed_scope_capture_save as subject
import tests.test_revenue_mvp_fixed_scope_private_save as fixtures


class CaptureSaveTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.PrivateSaveTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.master=bytes(range(32))  # Synthetic fixture only.
        self.assertEqual(len(self.master),32)
        self.output=self.fixture.output
        self.read=patch.object(subject.protected,'read_protected_key',return_value=self.master)
        self.key=self.read.start(); self.addCleanup(self.read.stop)
        self.bound_patch=patch.object(subject.capture.reader,'bound',return_value=True)
        self.bound=self.bound_patch.start(); self.addCleanup(self.bound_patch.stop)
        self.capture_patch=patch.object(subject.capture,'capture',return_value=(
            dict(status='FIVE_ITEM_CAPTURE_READY',api_calls=5),self.fixture.evidence))
        self.capture=self.capture_patch.start(); self.addCleanup(self.capture_patch.stop)

    def run_case(self,**changes):
        args=dict(expected_source_sha256=sha256(self.fixture.source).hexdigest(),
            expected_database_sha256='a'*64,batch_index=0,execute=True,
            confirmation=subject.CONFIRMATION,
            capture_confirmation=subject.capture.confirmation_for(0),
            key_confirmation=subject.protected.READ_CONFIRMATION,
            save_confirmation=subject.private_save.CONFIRMATION)
        args.update(changes)
        root=self.fixture.root
        return subject.run(root/'source.html',root/'fixture.db',root/'dummy.env',self.output,**args)

    def test_default_and_each_missing_confirmation_no_side_effect(self):
        for changes in ({'execute':False},{'confirmation':None},{'capture_confirmation':None},
                        {'key_confirmation':None},{'save_confirmation':None},{'batch_index':True}):
            result=self.run_case(**changes)
            self.assertEqual(result['status'],'BLOCKED')
        self.key.assert_not_called(); self.capture.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_success_uses_separated_key_and_preserves_api_count(self):
        result=self.run_case()
        self.assertEqual(result['status'],'PRIVATE_FIXED_FIVE_ARCHIVE_SAVED')
        self.assertEqual(result['api_calls'],5)
        self.assertFalse(result['publication_allowed'])
        self.assertTrue(result['key_read_performed'])
        args=dict(expected_database_sha256='a'*64,batch_index=0,evaluated_at=datetime.now(timezone.utc))
        derived=hmac.new(self.master,subject.KEY_DOMAIN,'sha256').digest()
        self.assertNotEqual(derived,self.master)
        verified=subject.capture.verify(self.output.read_bytes(),self.fixture.source,
            authentication_key=derived,**args)
        self.assertEqual(verified['status'],'AUTHENTICATED_FORMAT_VERIFIED')
        self.assertEqual(subject.capture.verify(self.output.read_bytes(),self.fixture.source,
            authentication_key=self.master,**args)['status'],'BLOCKED')

    def test_existing_output_stops_before_key_or_api(self):
        self.output.write_bytes(b'KEEP')
        self.assertEqual(self.run_case()['reason_code'],'EXISTING_OUTPUT_REFUSED')
        self.key.assert_not_called(); self.capture.assert_not_called()
        self.assertEqual(self.output.read_bytes(),b'KEEP')

    def test_preflight_failure_no_key_or_api(self):
        self.bound.return_value=False
        self.assertEqual(self.run_case()['reason_code'],'PREFLIGHT_UNCONFIRMED')
        self.key.assert_not_called(); self.capture.assert_not_called()

    def test_environment_missing_no_key_or_api(self):
        # Synthetic missing-path fixture; no credential file is read.
        missing=self.fixture.root/'absent.env'
        result=subject.run(self.fixture.root/'source.html',self.fixture.root/'fixture.db',
            missing,self.output,expected_source_sha256=sha256(self.fixture.source).hexdigest(),
            expected_database_sha256='a'*64,execute=True,confirmation=subject.CONFIRMATION,
            capture_confirmation=subject.capture.confirmation_for(0),
            key_confirmation=subject.protected.READ_CONFIRMATION,save_confirmation=subject.private_save.CONFIRMATION)
        self.assertEqual(result['reason_code'],'INPUT_BOUNDARY_INVALID')
        self.key.assert_not_called(); self.capture.assert_not_called()

    def test_key_unavailable_no_api(self):
        self.key.side_effect=ValueError('synthetic secret detail')
        result=self.run_case()
        self.capture.assert_not_called()
        self.assertTrue(result['key_read_attempted'])
        self.assertFalse(result['key_read_performed'])
        self.assertNotIn('synthetic secret detail',str(result))

    def test_capture_failure_no_save(self):
        self.capture.return_value=(dict(status='BLOCKED',api_calls=2),None)
        with patch.object(subject.private_save,'save') as save:
            result=self.run_case()
            save.assert_not_called()
        self.assertEqual(result['api_calls'],2)
        self.assertFalse(self.output.exists())

    def test_save_failure_no_retry(self):
        with patch.object(subject.private_save.os,'fsync',side_effect=OSError('synthetic')):
            result=self.run_case()
        self.assertEqual(result['status'],'BLOCKED')
        self.assertTrue(result['manual_review_required'])
        self.assertEqual(self.capture.call_count,1)
        self.assertEqual(result['api_calls'],5)

    def test_unexpected_save_exception_is_uncertain_not_success(self):
        with patch.object(subject.private_save,'save',side_effect=RuntimeError('synthetic')):
            result=self.run_case()
        self.assertEqual(result['status'],'BLOCKED')
        self.assertTrue(result['manual_review_required'])
        self.assertTrue(result['partial_file_may_exist'])


if __name__=='__main__':
    unittest.main()
