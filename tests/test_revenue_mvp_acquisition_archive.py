from datetime import datetime,timezone,timedelta
from hashlib import sha256
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import revenue_mvp_acquisition_archive as subject
import tests.test_revenue_mvp_fixed_scope_acquisition_evidence as fixtures


class AcquisitionArchiveTests(fixtures.AcquisitionEvidenceTests):
    # Deliberately fake test key; no real credential is generated or read.
    key=b'fixture-authentication-key-only!!'

    def archive(self):
        return subject.encode(self.capture(),self.source.read_bytes(),self.candidate,
                              authentication_key=self.key)

    def decode(self,data,**kwargs):
        options=dict(expected_database_sha256=self.db_hash,authentication_key=self.key)
        options.update(kwargs)
        return subject.decode(data,self.source.read_bytes(),self.candidate,**options)

    def test_authenticated_roundtrip_rebuilds_reviewable_not_publication_evidence(self):
        data=self.archive()
        evidence=self.decode(data)
        self.assertTrue(fixtures.subject.review(evidence,self.source.read_bytes(),self.candidate))
        self.assertTrue(evidence.summary()['authenticated_archive_loaded'])
        self.assertFalse(evidence.summary()['durable_receipt_available'])
        self.assertFalse(evidence.summary()['publication_allowed'])
        for secret in (self.key,b'fixture-',b'https://',b'affiliateURL',b'price_raw'):
            self.assertNotIn(secret,data)

    def test_changed_record_or_key_or_database_rejected(self):
        data=self.archive()
        changed=json.loads(data)
        changed['payload']['records'][0]['affiliate_target_valid']=False
        for candidate,kwargs in ((json.dumps(changed).encode(),{}),
                                  (data,{'authentication_key':b'other-key-for-fixture-only-1234567'}),
                                  (data,{'expected_database_sha256':'0'*64})):
            with self.assertRaises(ValueError): self.decode(candidate,**kwargs)

    def test_expired_and_future_receipts_rejected_after_reload(self):
        data=self.archive()
        for stamp in (datetime.now(timezone.utc)+timedelta(hours=25),
                      datetime.now(timezone.utc)-timedelta(hours=1)):
            with self.assertRaises(ValueError): self.decode(data,evaluated_at=stamp)

    def test_weak_key_unsigned_json_and_duplicate_fields_rejected(self):
        data=self.archive()
        with self.assertRaises(ValueError): self.decode(data,authentication_key=b'short')
        with self.assertRaises(ValueError): self.decode(b'{"verified":true,"count":100}')
        with self.assertRaises(ValueError): self.decode(b'{"payload":{},"payload":{},"authentication":"x"}')

    def test_private_save_requires_confirmation_and_refuses_overwrite(self):
        evidence=self.capture()
        output=Path(self.temp.name)/'private-archive.json'
        with self.assertRaises(ValueError):
            subject.save(evidence,self.source.read_bytes(),self.candidate,output,
                         authentication_key=self.key)
        self.assertFalse(output.exists())
        result=subject.save(evidence,self.source.read_bytes(),self.candidate,output,
            authentication_key=self.key,confirmation=subject.SAVE_CONFIRMATION)
        self.assertFalse(result['publication_allowed'])
        loaded=subject.load(output,self.source.read_bytes(),self.candidate,
            expected_archive_sha256=result['archive_sha256'],expected_database_sha256=self.db_hash,
            authentication_key=self.key)
        self.assertEqual(loaded.api_calls,100)
        with self.assertRaises(FileExistsError):
            subject.save(evidence,self.source.read_bytes(),self.candidate,output,
                authentication_key=self.key,confirmation=subject.SAVE_CONFIRMATION)

    def test_repo_path_and_changed_file_hash_rejected(self):
        with self.assertRaises(ValueError): subject._private_path(subject.ROOT/'archive.json')
        output=Path(self.temp.name)/'fixture.json'
        output.write_bytes(self.archive())
        with self.assertRaises(ValueError):
            subject.load(output,self.source.read_bytes(),self.candidate,
                expected_archive_sha256='0'*64,expected_database_sha256=self.db_hash,
                authentication_key=self.key)

    def test_changed_candidate_rejected_after_authentication(self):
        with self.assertRaises(ValueError):
            subject.decode(self.archive(),self.source.read_bytes(),b'other',
                expected_database_sha256=self.db_hash,authentication_key=self.key)

    def test_unowned_handwritten_evidence_cannot_be_signed(self):
        with self.assertRaises(ValueError):
            subject.encode({'verified':True},self.source.read_bytes(),self.candidate,
                           authentication_key=self.key)
