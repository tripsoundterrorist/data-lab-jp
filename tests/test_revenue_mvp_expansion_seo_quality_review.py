from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_expansion_seo_quality_review as subject  # noqa: E402


class ExpansionSeoQualityReviewTests(unittest.TestCase):
    def test_current_structure_is_reviewed_but_remains_noindex(self):
        result = subject.review()
        self.assertEqual(result.status, subject.REVIEWED)
        self.assertEqual(result.current_item_count, 100)
        self.assertEqual(result.target_item_count, 300)
        self.assertEqual(result.complete_card_count, 100)
        self.assertEqual(result.unique_cta_route_count, 100)
        self.assertTrue(result.seo_quality_reviewed)
        self.assertFalse(result.indexing_allowed)
        self.assertFalse(result.detail_page_generation_allowed)
        self.assertFalse(result.sitemap_change_allowed)
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.candidate_render_performance_verified)

    def test_missing_noindex_blocks_review(self):
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
        self.assertEqual(result.status, subject.BLOCKED)
        self.assertIn("LISTING_NOINDEX_MISSING", result.reason_codes)

    def test_duplicate_cta_route_blocks_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._copy_sources(Path(directory))
            listing = root / "items" / "index.html"
            text = listing.read_text(encoding="utf-8")
            routes = subject.PUBLIC_ID_ROUTE.pattern
            self.assertTrue(routes)
            import re
            matches = list(re.finditer(r'/go/itm_[0-9a-f]{24}', text))
            self.assertGreaterEqual(len(matches), 2)
            first = matches[0].group(0)
            second = matches[1].group(0)
            listing.write_text(text.replace(second, first, 1), encoding="utf-8")
            result = subject.review(root)
        self.assertIn("CTA_ROUTE_DUPLICATE", result.reason_codes)

    @staticmethod
    def _copy_sources(root: Path) -> Path:
        (root / "items").mkdir(parents=True)
        shutil.copy2(ROOT / "items" / "index.html", root / "items" / "index.html")
        shutil.copy2(ROOT / "items" / "item.html", root / "items" / "item.html")
        shutil.copy2(ROOT / "sitemap.xml", root / "sitemap.xml")
        return root


if __name__ == "__main__":
    unittest.main()
