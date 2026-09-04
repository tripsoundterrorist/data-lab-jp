from pathlib import Path
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest


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
    "items/index.html", "items/item.html", "items/items.css", "items/items.js",
}


class RevenueMvpStaticBuildTests(unittest.TestCase):
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
