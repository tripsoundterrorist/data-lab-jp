from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_expansion_sitemap_capacity_review as subject  # noqa: E402


class ExpansionSitemapCapacityReviewTests(unittest.TestCase):
    def test_current_sources_verify_capacity_without_authorizing_publication(self):
        result = subject.review()
        self.assertEqual(result.status, subject.VERIFIED)
        self.assertTrue(result.sitemap_capacity_verified)
        self.assertEqual(result.target_item_count, 300)
        self.assertEqual(result.target_additional_sitemap_urls, 0)
        self.assertFalse(result.seo_quality_reviewed)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.sitemap_change_allowed)
        self.assertEqual(set(result.source_sha256), {
            "sitemap.xml", "robots.txt", "items/index.html", "items/item.html",
        })

    def test_item_url_in_sitemap_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._copy_sources(Path(directory))
            sitemap = root / "sitemap.xml"
            text = sitemap.read_text(encoding="utf-8").replace(
                "</urlset>",
                "  <url><loc>https://datalabx.jp/items/</loc></url>\n</urlset>",
            )
            sitemap.write_text(text, encoding="utf-8")
            result = subject.review(root)
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertIn("ITEM_SURFACE_UNEXPECTEDLY_INDEXED", result.reason_codes)

    def test_missing_noindex_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._copy_sources(Path(directory))
            listing = root / "items" / "index.html"
            listing.write_text(
                listing.read_text(encoding="utf-8").replace(
                    '<meta name="robots" content="noindex,nofollow">', ""
                ),
                encoding="utf-8",
            )
            result = subject.review(root)
        self.assertIn("ITEM_LISTING_NOINDEX_MISSING", result.reason_codes)
        self.assertFalse(result.sitemap_capacity_verified)

    def test_missing_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subject.review(Path(directory))
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertIn("SOURCE_EVIDENCE_INVALID", result.reason_codes)

    @staticmethod
    def _copy_sources(root: Path) -> Path:
        (root / "items").mkdir(parents=True)
        for name in ("sitemap.xml", "robots.txt"):
            shutil.copy2(ROOT / name, root / name)
        for name in ("index.html", "item.html"):
            shutil.copy2(ROOT / "items" / name, root / "items" / name)
        return root


if __name__ == "__main__":
    unittest.main()
