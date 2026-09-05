from pathlib import Path
from types import SimpleNamespace
import json
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import revenue_mvp_local_preview as preview  # noqa: E402


class StaticBuilder:
    def resolve_repo_root(self, root):
        return root

    def collect_sources(self, _root):
        return {
            "index.html": b"shell",
            "items/items.js": b"script",
            "robots.txt": b"production robots",
        }

    def read_known_secret_values(self, _root):
        return ()

    def validate_files(self, _files, _secrets):
        return None


class LocalPreviewTests(unittest.TestCase):
    def test_valid_closed_candidate_builds_temp_preview_without_publication(self):
        candidate = {
            "manifest.json": json.dumps({
                "publication_status": "local_validation_only",
                "rights_review_required": ["title"],
            }).encode(),
            "index.json": b"{}",
            "items/00/itm_000000000000000000000000.json": b"{}",
        }
        validation = SimpleNamespace(
            artifact_validation="PASS", item_count=1, shard_count=1
        )
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "preview"
            with (
                mock.patch.object(preview, "_read_candidate", return_value=candidate),
                mock.patch.object(preview, "validate_artifacts", return_value=validation),
                mock.patch.object(preview, "_load_static_builder", return_value=StaticBuilder()),
            ):
                result = preview.build_preview(Path("candidate"), output)
            self.assertEqual(result.status, preview.LOCAL_PREVIEW_READY)
            self.assertEqual((output / "data" / "manifest.json").read_bytes(), candidate["manifest.json"])
            self.assertEqual(
                (output / "data" / "items" / "00" / "itm_000000000000000000000000.json").read_bytes(),
                b"{}",
            )
            self.assertEqual((output / "robots.txt").read_text(), "User-agent: *\nDisallow: /\n")
        self.assertFalse(result.publication_allowed)
        self.assertFalse(result.production_write_performed)

    def test_public_candidate_is_rejected(self):
        candidate = {
            "manifest.json": json.dumps({
                "publication_status": "public",
                "rights_review_required": [],
            }).encode()
        }
        validation = SimpleNamespace(
            artifact_validation="PASS", item_count=1, shard_count=1
        )
        with tempfile.TemporaryDirectory() as temporary:
            with (
                mock.patch.object(preview, "_read_candidate", return_value=candidate),
                mock.patch.object(preview, "validate_artifacts", return_value=validation),
            ):
                result = preview.build_preview(
                    Path("candidate"), Path(temporary) / "preview"
                )
        self.assertEqual(result.status, preview.FAIL_CLOSED)
        self.assertFalse(result.publication_allowed)

    def test_existing_or_non_temp_output_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            existing = preview.build_preview(Path("candidate"), Path(temporary))
        self.assertEqual(existing.status, preview.FAIL_CLOSED)
        outside = preview.build_preview(Path("candidate"), ROOT / "preview")
        self.assertEqual(outside.status, preview.FAIL_CLOSED)


class LocalPreviewBrowserGateTests(unittest.TestCase):
    def test_local_preview_requires_loopback_and_is_labeled_non_public(self):
        script = (ROOT / "items" / "items.js").read_text(encoding="utf-8")
        self.assertIn('["localhost", "127.0.0.1", "::1"]', script)
        self.assertIn('manifest?.publication_status === "local_validation_only"', script)
        self.assertIn('rights?.length > 0', script)
        self.assertIn('ローカルプレビュー（非公開）', script)
        self.assertIn('manifest?.publication_status === EXPECTED_PUBLICATION_STATUS', script)


if __name__ == "__main__":
    unittest.main()
