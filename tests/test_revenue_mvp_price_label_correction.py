from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import revenue_mvp_price_label_correction as subject
from revenue_mvp_product_card_reconciliation import reconcile


class PriceLabelTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"fixture.db"
        with sqlite3.connect(self.db) as c:
            c.executescript("""
                CREATE TABLE items(id INTEGER,site TEXT,service TEXT,floor TEXT,content_id TEXT,image_url_large TEXT);
                CREATE TABLE item_snapshots(item_id INTEGER,observed_at TEXT,price_raw TEXT,price_min INTEGER,id INTEGER);
                CREATE TABLE item_snapshot_titles(snapshot_id INTEGER,title TEXT,observed_at TEXT);
                INSERT INTO items VALUES(1,'FANZA','digital','videoa','fixture-1','https://pics.dmm.co.jp/fixture.jpg');
                INSERT INTO item_snapshots VALUES(1,'2026-10-01T00:00:00Z','1200~',1200,1);
                INSERT INTO item_snapshot_titles VALUES(1,'fixture','2026-10-01T00:00:00Z');
            """)
        self.source=b'<article class="item"><h2>fixture</h2><p class="price">1,200'+ '円'.encode()+b'</p><time>2026-10-01T00:00:00Z</time></article>'

    def set_raw(self,value):
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE item_snapshots SET price_raw=?",(value,))

    def test_lower_bound_only_and_idempotent(self):
        original=self.db.read_bytes()
        corrected=subject.correct(self.source,self.db)
        self.assertIn('1,200円〜',corrected.decode())
        self.assertEqual(subject.correct(corrected,self.db),corrected)
        self.assertEqual(len(reconcile(corrected,self.db)),1)
        self.assertEqual(self.db.read_bytes(),original)

    def test_exact_price_not_lower_bound(self):
        self.set_raw("1200")
        self.assertEqual(subject.correct(self.source,self.db),self.source)

    def test_missing_malformed_or_inconsistent_raw_stops(self):
        for value in (None,"","unknown","1300~","1200~1300"):
            self.set_raw(value)
            with self.subTest(value=value),self.assertRaises(ValueError):
                subject.correct(self.source,self.db)

    def test_duplicate_snapshot_stops(self):
        with sqlite3.connect(self.db) as c:
            c.execute("INSERT INTO item_snapshots SELECT item_id,observed_at,price_raw,price_min,2 FROM item_snapshots")
        with self.assertRaises(ValueError):
            subject.correct(self.source,self.db)

    def test_staging_preserves_candidate_and_restores_only_label_delta(self):
        source = Path(self.temp.name)/"source.html"
        output = Path(self.temp.name)/"review.html"
        candidate = subject.correct(self.source,self.db)
        source.write_bytes(candidate)
        result = subject.stage_candidate(source,self.db,self.source,output)
        self.assertEqual(source.read_bytes(),self.source)
        self.assertEqual(output.read_bytes(),candidate)
        self.assertFalse(result["publication_allowed"])
        with self.assertRaises(ValueError):
            subject.stage_candidate(source,self.db,self.source,output)

    def test_staging_refuses_unrelated_local_edits(self):
        source = Path(self.temp.name)/"source.html"
        output = Path(self.temp.name)/"review.html"
        source.write_bytes(subject.correct(self.source,self.db)+b"unrelated")
        with self.assertRaises(ValueError):
            subject.stage_candidate(source,self.db,self.source,output)
        self.assertFalse(output.exists())
        self.assertTrue(source.read_bytes().endswith(b"unrelated"))

    def test_sidecar_stops(self):
        Path(str(self.db)+"-wal").write_bytes(b"fixture")
        with self.assertRaises(ValueError):
            subject.correct(self.source,self.db)


if __name__=="__main__":
    unittest.main()
