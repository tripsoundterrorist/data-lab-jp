"""Local public-candidate metadata does not activate publication."""
import ast
from pathlib import Path
import unittest

from scripts.coupon_help_public_candidate import render_candidate, SITE_LINKS

ROOT = Path(__file__).resolve().parents[1]


class CouponPublicCandidateTests(unittest.TestCase):
    def setUp(self):
        self.draft = (ROOT / 'preview/coupon-help.html').read_text(encoding='utf-8')

    def test_candidate_metadata_and_navigation_stay_unpublished(self):
        candidate = render_candidate(self.draft)
        self.assertIn('href="https://datalabx.jp/coupon-help"', candidate)
        self.assertNotIn('DATA LAB ローカル案</title>', candidate)
        self.assertIn('name="robots" content="noindex, nofollow"', candidate)
        self.assertIn('未公開の下書きです。公開審査・公開承認は未完了です。', candidate)
        for path, label in SITE_LINKS:
            self.assertIn(f'<a href="{path}">{label}</a>', candidate)
        self.assertNotIn('<script', candidate)
        self.assertNotIn('href="/items/', candidate)
        self.assertNotIn('href="/go/', candidate)

    def test_source_is_not_mutated(self):
        render_candidate(self.draft)
        self.assertEqual(self.draft, (ROOT / 'preview/coupon-help.html').read_text(encoding='utf-8'))

    def test_missing_safety_markers_fail_closed(self):
        for bad in (
            self.draft.replace('noindex, nofollow', 'index, follow'),
            self.draft.replace('公開審査・公開承認は未完了です。', ''),
            self.draft.replace('DATA LAB ローカル案</title>', 'changed</title>'),
            self.draft.replace('</head>', '<link rel="canonical" href="https://example.invalid"></head>'),
            self.draft + '<script src="https://example.invalid"></script>',
            self.draft + '<a onclick="bad()">test</a>',
        ):
            with self.subTest(bad=bad[-60:]):
                with self.assertRaises(ValueError):
                    render_candidate(bad)

    def test_candidate_route_not_in_deployment_allowlist_or_sitemap(self):
        tree = ast.parse((ROOT / 'scripts/build-static-site.py').read_text(encoding='utf-8'))
        assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == 'ALLOWLIST' for t in node.targets)]
        self.assertEqual(len(assignments), 1)
        self.assertNotIn('coupon-help.html', ast.literal_eval(assignments[0].value))
        for path in ('sitemap.xml', 'index.html', 'column-price.html'):
            self.assertNotIn('coupon-help', (ROOT / path).read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
