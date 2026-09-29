from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_product_card_reconciliation as subject  # noqa: E402


STAMP = "2026-09-21T15:59:45Z"


class ProductCardReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "fixture.db"
        with sqlite3.connect(self.db) as connection:
            connection.executescript("""
                CREATE TABLE items (
                    id INTEGER PRIMARY KEY, site TEXT, service TEXT, floor TEXT,
                    content_id TEXT, image_url_large TEXT
                );
                CREATE TABLE item_snapshots (
                    id INTEGER PRIMARY KEY, item_id INTEGER,
                    observed_at TEXT, price_min INTEGER
                );
                CREATE TABLE item_snapshot_titles (
                    snapshot_id INTEGER, title TEXT, observed_at TEXT
                );
            """)
            connection.execute(
                "INSERT INTO items VALUES (1,?,?,?,?,?)",
                ("FANZA", "digital", "videoa", "fixture-001",
                 "https://pics.dmm.co.jp/digital/video/fixture/fixturepl.jpg"),
            )
            connection.execute(
                "INSERT INTO item_snapshots VALUES (1,1,?,1200)", (STAMP,),
            )
            connection.execute(
                "INSERT INTO item_snapshot_titles VALUES (1,'架空の商品',?)", (STAMP,),
            )

    def source(self, title="架空の商品"):
        return (
            '<main><article class="item"><h2>' + title + '</h2>'
            '<p class="price">1,200円</p><time>' + STAMP
            + '</time></article></main>'
        ).encode()

    def test_exact_card_binds_to_private_identity_and_official_image(self):
        cards = subject.reconcile(self.source(), self.db)
        self.assertEqual(len(cards), 1)
        self.assertRegex(cards[0].public_id, r"^itm_[0-9a-f]{24}$")
        self.assertEqual(cards[0].content_id, "fixture-001")
        self.assertTrue(cards[0].image_url.startswith("https://pics.dmm.co.jp/"))

    def test_missing_binding_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "LIVE_CARD_BINDING_NOT_UNIQUE"):
            subject.reconcile(self.source("別の商品"), self.db)

    def test_non_official_image_host_fails_closed(self):
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                "UPDATE items SET image_url_large='https://example.invalid/image.jpg'"
            )
        with self.assertRaisesRegex(ValueError, "PRODUCT_CARD_ASSET_INVALID"):
            subject.reconcile(self.source(), self.db)

    def test_enrichment_adds_official_image_and_opaque_cta_only(self):
        card = subject.reconcile(self.source(), self.db)[0]
        rendered = subject.enrich(self.source(), self.db, frozenset({card.public_id}))
        text = rendered.decode()
        self.assertEqual(text.count('class="card-image"'), 1)
        self.assertEqual(text.count('class="affiliate-cta-block"'), 1)
        self.assertIn(f'href="/go/{card.public_id}"', text)
        self.assertNotIn(card.content_id, text)
        self.assertNotIn("affiliateURL", text)

    def test_enrichment_requires_explicit_known_cta_scope(self):
        for selected in (frozenset(), frozenset({"itm_000000000000000000000000"})):
            with self.subTest(selected=selected), self.assertRaisesRegex(
                ValueError, "CTA_SCOPE_INVALID"
            ):
                subject.enrich(self.source(), self.db, selected)


if __name__ == "__main__":
    unittest.main()
