from pathlib import Path
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "revenue_mvp_static_build", ROOT / "scripts/build-static-site.py"
)
assert SPEC is not None and SPEC.loader is not None
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


EXPECTED_PUBLIC_FILES = {
    "_headers", "404.html", "about.html", "analytics-consent.css", "analytics-consent.js",
    "column-price.html", "column-score.html", "column-trend.html",
    "contact.html", "disclosure.html", "index.html", "legal.css",
    "privacy.html", "robots.txt", "sitemap.xml", "terms.html",
    "items/index.html", "items/item.html", "items/items.css", "items/discovery.js", "items/items.js",
}


class RevenueMvpStaticBuildTests(unittest.TestCase):
    def test_real_build_preserves_public_bytes_and_excludes_internal_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            replica = Path(temporary) / "repo"
            replica.mkdir()
            for relative in build.ALLOWLIST:
                destination = replica / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, destination)
            for relative in (
                "preview/coupon-help.html", "docs/internal.md", "tests/internal.py",
                "data/private.db", "runtime/private/audit.json", "wrangler.toml",
            ):
                destination = replica / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(b"INTERNAL_FIXTURE_NOT_FOR_PUBLICATION")
            output = replica / "dist"
            output.mkdir()
            (output / "stale-internal.txt").write_bytes(b"STALE_FIXTURE")
            process = subprocess.run(
                [sys.executable, str(ROOT / "scripts/build-static-site.py"),
                 "--repo-root", str(replica)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            actual = {path.relative_to(output).as_posix(): path.read_bytes()
                      for path in output.rglob("*") if path.is_file()}
            self.assertEqual(set(actual), EXPECTED_PUBLIC_FILES)
            for relative, content in actual.items():
                self.assertEqual(content, (ROOT / relative).read_bytes(), relative)
                self.assertNotIn(b"INTERNAL_FIXTURE_NOT_FOR_PUBLICATION", content)
                self.assertNotIn(b"STALE_FIXTURE", content)

    def test_current_catalog_is_static_and_preserved_in_allowlist(self):
        class CatalogParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.cards = 0
                self.scripts = []

            def handle_starttag(self, tag, attrs):
                values = dict(attrs)
                if tag == "article":
                    self.cards += 1
                if tag == "script":
                    self.scripts.append(values.get("src", ""))

        files = build.collect_sources(ROOT)
        catalog = CatalogParser()
        catalog.feed(files["items/index.html"].decode("utf-8"))
        self.assertEqual(catalog.cards, 100)
        self.assertIn("discovery.js?v=20260930", catalog.scripts)
        self.assertFalse(any(src.split("?")[0].endswith("items.js")
                             for src in catalog.scripts))
        self.assertIn("items/discovery.js", files)
        self.assertIn("items/items.css", files)

    def test_allowlist_contains_complete_current_public_shell(self):
        self.assertEqual(set(build.ALLOWLIST), EXPECTED_PUBLIC_FILES)
        self.assertEqual(len(build.ALLOWLIST), len(set(build.ALLOWLIST)))

    def test_allowlist_excludes_internal_and_unreleased_files(self):
        for forbidden in (
            ".env", ".env.example", "data/data-lab.db", "db/schema.sql",
            "scripts/build-public-data.py", "preview/index.html", "AGENTS.md",
        ):
            self.assertNotIn(forbidden, build.ALLOWLIST)

    def test_real_source_collection_and_validation_pass(self):
        files = build.collect_sources(ROOT)
        build.validate_files(files, ())
        self.assertEqual(set(files), EXPECTED_PUBLIC_FILES)

    def test_dry_run_does_not_create_dist(self):
        with tempfile.TemporaryDirectory() as temporary:
            replica = Path(temporary) / "repo"
            replica.mkdir()
            for relative in build.ALLOWLIST:
                destination = replica / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, destination)
            process = subprocess.run(
                [sys.executable, str(ROOT / "scripts/build-static-site.py"),
                 "--repo-root", str(replica), "--dry-run"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertIn(f"Files: {len(EXPECTED_PUBLIC_FILES)}", process.stdout)
            self.assertFalse((replica / "dist").exists())

    def test_missing_public_file_fails_closed(self):
        files = build.collect_sources(ROOT)
        files.pop("privacy.html")
        with self.assertRaises(build.ValidationError):
            build.validate_files(files, ())

    def test_known_secret_in_public_asset_fails_closed(self):
        files = build.collect_sources(ROOT)
        files["index.html"] += b"fixture-secret-value"
        with self.assertRaises(build.ValidationError):
            build.validate_files(files, (b"fixture-secret-value",))


if __name__ == "__main__":
    unittest.main()
