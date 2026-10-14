from hashlib import sha256
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import revenue_mvp_price_display_release as subject
from tests.test_revenue_mvp_price_display_transition import Response


class DisplayReleaseTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "fixture.db"
        with sqlite3.connect(self.db) as connection:
            connection.executescript("""
                CREATE TABLE items(id INTEGER,site TEXT,service TEXT,floor TEXT,content_id TEXT,image_url_large TEXT);
                CREATE TABLE item_snapshots(item_id INTEGER,observed_at TEXT,price_raw TEXT,price_min INTEGER,id INTEGER);
                CREATE TABLE item_snapshot_titles(snapshot_id INTEGER,title TEXT,observed_at TEXT);
            """)
            for index in range(100):
                connection.execute("INSERT INTO items VALUES(?,'FANZA','digital','videoa',?,'https://pics.dmm.co.jp/fixture.jpg')", (index, f"fixture-{index}"))
                connection.execute("INSERT INTO item_snapshots VALUES(?,'2026-10-01T00:00:00Z','1200~',1200,?)", (index,index))
                connection.execute("INSERT INTO item_snapshot_titles VALUES(?,?,'2026-10-01T00:00:00Z')", (index,f"fixture-{index}"))
        self.old = ''.join(f'<article class="item"><h2>fixture-{i}</h2><p class="price">1,200円</p><time>2026-10-01T00:00:00Z</time></article>' for i in range(100)).encode()
        self.new = self.old.replace('円</p>'.encode(), '円〜</p>'.encode())
        self.history = {"items_artifact_sha256": sha256(self.old).hexdigest()}
        for name, value in (("BASELINE",sha256(self.old).hexdigest()),
                            ("CANDIDATE",sha256(self.new).hexdigest())):
            mock = patch.object(subject.transition,name,value)
            mock.start()
            self.addCleanup(mock.stop)
        self.original = self.db.read_bytes()
        self.db_hash = sha256(self.original).hexdigest()

    def assess(self, **kwargs):
        return subject.assess(self.old,self.new,self.db,self.db_hash,self.history,**kwargs)

    def test_offline_review_has_no_http_or_writes_or_publication(self):
        with patch.object(subject.transition.urllib.request,"urlopen",side_effect=AssertionError):
            result = self.assess()
        self.assertEqual(result.status,"DISPLAY_CANDIDATE_READY_FOR_SEPARATE_RELEASE_REVIEW")
        self.assertEqual(result.lower_bound_label_count,100)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.database_write_performed)
        self.assertFalse(result.historical_evidence_modified)
        self.assertFalse(result.current_eligibility_verified)
        self.assertEqual(self.db.read_bytes(), self.original)

    def test_display_match_never_reuses_snapshot_for_current_eligibility(self):
        with patch.object(subject.transition.urllib.request,"urlopen",return_value=Response(self.new)):
            observation = subject.transition.capture_public_page()
        result = self.assess(observation=observation)
        self.assertTrue(result.display_match_observed)
        self.assertFalse(result.current_eligibility_verified)
        self.assertFalse(result.publication_allowed)

    def test_database_identity_mismatch_blocks(self):
        self.assertEqual(subject.assess(self.old,self.new,self.db,"0"*64,self.history).status,"BLOCKED")

    def test_raw_price_disagreement_blocks_even_with_updated_database_hash(self):
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE item_snapshots SET price_raw='1200' WHERE item_id=0")
        digest = sha256(self.db.read_bytes()).hexdigest()
        self.assertEqual(subject.assess(self.old,self.new,self.db,digest,self.history).reason_code,
                         "PRICE_RAW_PROVENANCE_MISMATCH")

    def test_unrelated_delta_and_fake_capture_block(self):
        self.assertEqual(subject.assess(self.old,self.new+b"other",self.db,self.db_hash,self.history).status,"BLOCKED")
        self.assertEqual(self.assess(observation={"verified":True}).status,"BLOCKED")

    def test_database_sidecar_blocks(self):
        Path(str(self.db)+"-wal").write_bytes(b"fixture")
        self.assertEqual(self.assess().status,"BLOCKED")

    def test_handwritten_acquisition_evidence_cannot_unlock_release_review(self):
        self.assertEqual(self.assess(acquisition_evidence={"verified":True,"count":100}).reason_code,
                         "CURRENT_ACQUISITION_EVIDENCE_INVALID")

    def test_valid_acquisition_review_still_requires_explicit_publication_approval(self):
        from types import SimpleNamespace
        with patch.object(subject.acquisition,"review",return_value=True):
            result=self.assess(acquisition_evidence=SimpleNamespace(database_sha256=self.db_hash))
        self.assertTrue(result.current_eligibility_verified)
        self.assertFalse(result.publication_allowed)
        self.assertTrue(result.explicit_release_approval_required)
