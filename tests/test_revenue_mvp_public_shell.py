from html.parser import HTMLParser
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ORIGIN = "https://datalabx.jp"
INDEXABLE = {
    "index.html": f"{PUBLIC_ORIGIN}/",
    "column-price.html": f"{PUBLIC_ORIGIN}/column-price.html",
    "column-trend.html": f"{PUBLIC_ORIGIN}/column-trend.html",
    "column-score.html": f"{PUBLIC_ORIGIN}/column-score.html",
    "about.html": f"{PUBLIC_ORIGIN}/about.html",
    "disclosure.html": f"{PUBLIC_ORIGIN}/disclosure.html",
    "privacy.html": f"{PUBLIC_ORIGIN}/privacy.html",
    "terms.html": f"{PUBLIC_ORIGIN}/terms.html",
    "contact.html": f"{PUBLIC_ORIGIN}/contact.html",
}


class DocumentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.meta = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "a" and "href" in values:
            self.links.append(values["href"])
        if tag == "link" and values.get("rel") == "canonical":
            self.meta.append(("canonical", values.get("href")))
        if tag == "meta":
            key = values.get("property") or values.get("name")
            if key:
                self.meta.append((key, values.get("content")))


def parse(path):
    parser = DocumentParser()
    parser.feed((ROOT / path).read_text(encoding="utf-8"))
    return parser


class RevenueMvpPublicShellTests(unittest.TestCase):
    def test_indexable_pages_have_exact_production_canonical(self):
        for path, expected in INDEXABLE.items():
            with self.subTest(path=path):
                self.assertEqual(parse(path).meta.count(("canonical", expected)), 1)

    def test_home_has_minimum_social_metadata(self):
        metadata = dict(parse("index.html").meta)
        self.assertEqual(metadata["og:url"], f"{PUBLIC_ORIGIN}/")
        self.assertEqual(metadata["og:type"], "website")
        self.assertEqual(metadata["twitter:card"], "summary")

    def test_legal_and_transparency_routes_are_linked_from_home(self):
        links = set(parse("index.html").links)
        required = {f"/{path}" for path in (
            "about.html", "disclosure.html", "privacy.html", "terms.html",
            "contact.html",
        )}
        self.assertTrue(required <= links)

    def test_home_links_to_fail_closed_product_catalog(self):
        document = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="/items/"', document)
        self.assertIn("作品データの公開状況を見る", document)
        self.assertIn("公開前のデータは表示しません", document)
        self.assertNotIn("作品データ A", document)
        self.assertNotIn("実データ取得前の表示確認用", document)

    def test_home_analytics_copy_matches_explicit_consent_behavior(self):
        document = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("明示的に同意いただいた場合に限り", document)
        self.assertIn("拒否しても基本機能を利用でき", document)

    def test_internal_absolute_links_resolve_to_tracked_files(self):
        for page in [*INDEXABLE, "404.html"]:
            for link in parse(page).links:
                if not link.startswith("/") or link == "/":
                    continue
                with self.subTest(page=page, link=link):
                    target = ROOT / link.lstrip("/")
                    if link.endswith("/"):
                        target = target / "index.html"
                    self.assertTrue(target.is_file())

    def test_404_is_not_indexable(self):
        self.assertIn(("robots", "noindex"), parse("404.html").meta)

    def test_robots_names_production_sitemap(self):
        robots = (ROOT / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("User-agent: *", robots)
        self.assertIn(f"Sitemap: {PUBLIC_ORIGIN}/sitemap.xml", robots)
        self.assertNotIn("pages.dev", robots)

    def test_sitemap_contains_only_declared_indexable_canonicals(self):
        root = ET.parse(ROOT / "sitemap.xml").getroot()
        namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locations = {node.text for node in root.findall("s:url/s:loc", namespace)}
        self.assertEqual(locations, set(INDEXABLE.values()))


if __name__ == "__main__":
    unittest.main()
