from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import revenue_mvp_archive_dpapi as subject


class DPAPIBridgeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/'fake.dpapi'
        self.path.write_bytes(b'fixture ciphertext only')
        mock=patch.object(subject,'KEY_PATH',self.path)
        mock.start(); self.addCleanup(mock.stop)
        folder=patch.object(subject,'EVIDENCE_DIRECTORY',self.path.parent)
        folder.start(); self.addCleanup(folder.stop)

    def test_no_automatic_key_read_without_confirmation(self):
        with patch.object(subject,'_unprotect') as decrypt:
            with self.assertRaises(ValueError): subject.read_protected_key()
            decrypt.assert_not_called()

    def test_acl_fail_does_not_decrypt(self):
        with patch.object(subject.os,'name','nt'),patch.object(subject,'_acl_safe',return_value=False),patch.object(subject,'_unprotect') as decrypt:
            with self.assertRaises(ValueError): subject.read_protected_key(confirmation=subject.READ_CONFIRMATION)
            decrypt.assert_not_called()

    def test_mock_read_is_memory_only_and_file_unchanged(self):
        before=self.path.read_bytes()
        with patch.object(subject.os,'name','nt'),patch.object(subject,'_acl_safe',return_value=True),patch.object(subject,'_unprotect',return_value=b'x'*32):
            self.assertEqual(len(subject.read_protected_key(confirmation=subject.READ_CONFIRMATION)),32)
        self.assertEqual(self.path.read_bytes(),before)

    def test_decrypt_error_sanitized(self):
        with patch.object(subject.os,'name','nt'),patch.object(subject,'_acl_safe',return_value=True),patch.object(subject,'_unprotect',side_effect=RuntimeError('secret fixture detail')):
            with self.assertRaises(ValueError) as error: subject.read_protected_key(confirmation=subject.READ_CONFIRMATION)
        self.assertEqual(str(error.exception),'PROTECTED_ARCHIVE_KEY_UNAVAILABLE')

    def test_unexpected_length_and_changed_file_refused(self):
        with patch.object(subject.os,'name','nt'),patch.object(subject,'_acl_safe',return_value=True),patch.object(subject,'_unprotect',return_value=b'x'*31):
            with self.assertRaises(ValueError): subject.read_protected_key(confirmation=subject.READ_CONFIRMATION)
        def changed(_):
            self.path.write_bytes(b'changed fixture ciphertext')
            return b'x'*32
        with patch.object(subject.os,'name','nt'),patch.object(subject,'_acl_safe',return_value=True),patch.object(subject,'_unprotect',side_effect=changed):
            with self.assertRaises(ValueError): subject.read_protected_key(confirmation=subject.READ_CONFIRMATION)

    def test_archive_save_requires_confirmation_before_key_read(self):
        with patch.object(subject,'read_protected_key') as read:
            with self.assertRaises(ValueError): subject.save_with_dpapi(None,b'',b'',self.path)
            read.assert_not_called()

    def test_outside_approved_evidence_folder_refused_before_key_read(self):
        with patch.object(subject,'read_protected_key') as read:
            with self.assertRaises(ValueError):
                subject.save_with_dpapi(None,b'',b'',self.path.parent/'other'/'archive.json',
                                        confirmation=subject.archive.SAVE_CONFIRMATION)
            read.assert_not_called()

    def test_acl_subprocess_returns_only_explicit_success_marker(self):
        from types import SimpleNamespace
        for code,stdout,expected in ((0,b'KEY_ACL_OK\r\n',True),
                                     (1,b'',False),(0,b'other output',False)):
            with patch.object(subject.subprocess,'run',return_value=SimpleNamespace(returncode=code,stdout=stdout)) as run:
                self.assertEqual(subject._acl_safe(),expected)
                self.assertTrue(run.call_args.kwargs['capture_output'])
                self.assertEqual(run.call_args.args[0][0],subject.POWERSHELL)

    def test_parent_exception_is_pinned_to_local_group_and_readonly_mask(self):
        from types import SimpleNamespace
        with patch.object(subject.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=b'KEY_ACL_OK')) as run:
            self.assertTrue(subject._acl_safe())
        script=run.call_args.args[0][-1]
        self.assertIn("$env:COMPUTERNAME,'CodexSandboxUsers'",script)
        self.assertIn("$path -eq 'C:\\Users\\User\\.data-lab-private'",script)
        self.assertIn("ReadAndExecute,Synchronize",script)
        self.assertIn("PARENT_SANDBOX_WRITE_OR_DENY_REFUSED",script)
        self.assertIn("$acl.AreAccessRulesProtected",script)
        self.assertIn("$seen.Count -ne 2",script)

    def test_wrappers_pass_mock_key_only_to_archive(self):
        with patch.object(subject,'read_protected_key',return_value=b'x'*32),patch.object(subject.archive,'save',return_value={'publication_allowed':False}) as save:
            result=subject.save_with_dpapi(None,b'old',b'new',self.path,confirmation=subject.archive.SAVE_CONFIRMATION)
            self.assertFalse(result['publication_allowed'])
            self.assertEqual(save.call_args.kwargs['authentication_key'],b'x'*32)
        with patch.object(subject,'read_protected_key',return_value=b'x'*32),patch.object(subject.archive,'load',return_value='fixture verified'):
            self.assertEqual(subject.load_with_dpapi(self.path,b'old',b'new',expected_archive_sha256='hash',expected_database_sha256='db',confirmation=subject.READ_CONFIRMATION),'fixture verified')
