from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import affiliate_cta_local_preview as preview  # noqa: E402


class AffiliateCtaLocalPreviewTests(unittest.TestCase):
    def test_builds_one_isolated_noindex_page_with_dummy_link(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "affiliate-cta-preview"
            result = preview.build_preview(output)
            document = (output / "index.html").read_text(encoding="utf-8")

        self.assertEqual(result.status, preview.LOCAL_PREVIEW_READY)
        self.assertTrue(result.local_preview_only)
        self.assertTrue(result.dummy_url_only)
        self.assertTrue(result.blocked_fixture_hidden)
        self.assertEqual(result.output_file_count, 1)
        self.assertFalse(result.production_write_performed)
        self.assertFalse(result.publication_allowed)
        self.assertIn('name="robots" content="noindex,nofollow"', document)
        self.assertIn(preview.DUMMY_URL, document)
        self.assertNotIn("dmm.co.jp", document.casefold())
        self.assertNotIn("fanza", document.casefold())

    def test_cta_and_proximate_disclosure_are_present_together(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "affiliate-cta-preview"
            result = preview.build_preview(output)
            document = (output / "index.html").read_text(encoding="utf-8")

        self.assertEqual(result.status, preview.LOCAL_PREVIEW_READY)
        disclosure_index = document.index('class="disclosure"')
        cta_index = document.index('class="cta"')
        self.assertLess(disclosure_index, cta_index)
        self.assertIn("PR：", document[disclosure_index:cta_index])
        self.assertIn("アフィリエイトリンク", document[disclosure_index:cta_index])
        self.assertIn('rel="noopener noreferrer sponsored"', document)

    def test_mobile_layout_and_touch_target_are_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "affiliate-cta-preview"
            result = preview.build_preview(output)
            document = (output / "index.html").read_text(encoding="utf-8")

        self.assertEqual(result.status, preview.LOCAL_PREVIEW_READY)
        self.assertIn("@media (max-width: 430px)", document)
        self.assertIn("main { padding: 24px 14px; }", document)
        self.assertIn(".cta { min-height: 48px; }", document)

    def test_existing_or_non_temp_output_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            existing = preview.build_preview(Path(temporary))
        self.assertEqual(existing.status, preview.FAIL_CLOSED)
        self.assertFalse(existing.publication_allowed)

        outside = preview.build_preview(ROOT / "affiliate-cta-preview")
        self.assertEqual(outside.status, preview.FAIL_CLOSED)
        self.assertFalse(outside.production_write_performed)

    def test_presentation_failure_writes_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "affiliate-cta-preview"
            with mock.patch.object(
                preview.cta,
                "build_affiliate_cta",
                side_effect=RuntimeError("secret fixture detail"),
            ):
                result = preview.build_preview(output)

            self.assertEqual(result.status, preview.FAIL_CLOSED)
            self.assertFalse(output.exists())
            self.assertNotIn("secret", json.dumps(result.to_dict()))

    def test_safe_result_does_not_echo_dummy_or_output_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "affiliate-cta-preview"
            result = preview.build_preview(output)

        safe_output = json.dumps(result.to_dict(), sort_keys=True)
        self.assertNotIn(preview.DUMMY_URL, safe_output)
        self.assertNotIn(str(output), safe_output)

    def test_cli_is_machine_readable_and_non_deploying(self):
        with tempfile.TemporaryDirectory() as temporary:
            output_path = Path(temporary) / "affiliate-cta-preview"
            output = StringIO()
            with redirect_stdout(output):
                return_code = preview.main(["--output", str(output_path)])

        self.assertEqual(return_code, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], preview.LOCAL_PREVIEW_READY)
        self.assertFalse(result["production_write_performed"])
        self.assertFalse(result["publication_allowed"])


if __name__ == "__main__":
    unittest.main()
