from pathlib import Path
import unittest

from scripts.coupon_help_candidate_bundle import REQUIRED_INPUTS, build_candidate_bundle
from scripts.coupon_help_public_release import RELATED_PRICE_LINK, build_public_release

ROOT = Path(__file__).resolve().parents[1]


class CouponPublicReleaseTests(unittest.TestCase):
    def setUp(self):
        self.sources = {name: (ROOT / name).read_bytes() for name in REQUIRED_INPUTS}

    def test_related_link_describes_destination_scope(self):
        article = build_public_release(self.sources)['coupon-help.html'].decode('utf-8')
        self.assertIn('支払額や利用条件を比較するときは、', RELATED_PRICE_LINK)
        self.assertNotIn('還元ポイント', RELATED_PRICE_LINK)
        self.assertEqual(article.count(RELATED_PRICE_LINK), 1)
        self.assertIn('支払額と還元ポイントは別々に確認する', article)

    def test_single_related_link_after_final_note_before_article_end(self):
        article = build_public_release(self.sources)['coupon-help.html'].decode('utf-8')
        self.assertEqual(article.count('href="/column-price"'), 1)
        self.assertEqual(article.count(RELATED_PRICE_LINK), 1)
        self.assertLess(article.rindex('<p class="note">'), article.index(RELATED_PRICE_LINK))
        self.assertLess(article.index(RELATED_PRICE_LINK), article.index('</article>'))
        self.assertTrue((ROOT / 'column-price.html').is_file())

    def test_sources_and_review_candidate_unchanged(self):
        before = dict(self.sources)
        candidate = build_candidate_bundle(self.sources)
        build_public_release(self.sources)
        self.assertEqual(before, self.sources)
        self.assertNotIn(b'href="/column-price"', candidate['coupon-help.html'])
        self.assertEqual(candidate, build_candidate_bundle(self.sources))
        for name, content in before.items():
            self.assertEqual((ROOT / name).read_bytes(), content)

    def test_other_bundle_members_and_analytics_unchanged(self):
        candidate = build_candidate_bundle(self.sources)
        public = build_public_release(self.sources)
        self.assertEqual(set(public), set(candidate) - {'_headers'})
        for name in public:
            if name != 'coupon-help.html':
                self.assertEqual(public[name], candidate[name])
        article = public['coupon-help.html']
        self.assertEqual(article.count(b'src="/analytics-consent.js" defer'), 1)
        self.assertEqual(article.count(b'rel="canonical"'), 1)
        self.assertNotIn(b'noindex', article)
        self.assertNotIn(b'/go/', article)

    def test_duplicate_link_rejected(self):
        self.sources['preview/coupon-help.html'] = self.sources['preview/coupon-help.html'].replace(
            b'</article>', b'<a href="/column-price">duplicate</a></article>')
        with self.assertRaisesRegex(ValueError, 'RELATED_PRICE_LINK_ALREADY_PRESENT'):
            build_public_release(self.sources)

    def test_missing_or_duplicate_anchor_rejected(self):
        source = self.sources['preview/coupon-help.html']
        for replacement in (b'</article>\n</main>', b'  </article></main>  </article></main>'):
            with self.subTest(replacement=replacement):
                self.sources['preview/coupon-help.html'] = source.replace(
                    b'  </article></main>', replacement)
                with self.assertRaisesRegex(ValueError, 'CANDIDATE_SOURCE_CHANGED'):
                    build_public_release(self.sources)

    def test_repeat_build_is_deterministic(self):
        self.assertEqual(build_public_release(self.sources), build_public_release(self.sources))


if __name__ == '__main__':
    unittest.main()
