import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import x_static_card_mvp as card

ROOT = Path(__file__).resolve().parents[1]


class StaticCardTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT/"tests/fixtures/x-short-video-safe-v0.1.json").read_text(encoding="utf-8"))
        self.config = json.loads((ROOT/"config/x-short-video-mvp-v0.1.json").read_text(encoding="utf-8"))

    def test_invalid_input_no_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = copy.deepcopy(self.data)
            data["post_text"] = "あ"*141
            result = card.generate_card(data, self.config, Path(temporary))
            self.assertEqual(result["text_status"], "BLOCKED")
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_font_failure_preserves_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(card.shared, "_font_path", side_effect=ValueError("JAPANESE_FONT_MISSING")):
                result = card.generate_card(self.data, self.config, Path(temporary))
            self.assertEqual(result["text_status"], "READY")
            self.assertEqual(result["image_status"], "FAILED")
            self.assertIsNone(result["image_path"])

    def test_deterministic_png(self):
        try:
            card.shared._font_path(None)
        except ValueError:
            self.skipTest("Japanese font unavailable")
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            first = card.generate_card(self.data, self.config, output)
            second = card.generate_card(self.data, self.config, output)
            self.assertEqual(first["image_status"], "READY")
            self.assertEqual(first["image_sha256"], second["image_sha256"])
            self.assertEqual(len(list(output.glob("*.png"))), 1)
            with Image.open(first["image_path"]) as image:
                self.assertEqual(image.size, (1200, 1500))
            self.assertFalse(first["upload_performed"])
            self.assertFalse(first["posting_performed"])

    def test_safety_gates(self):
        for field, value in (("sensitive_media", True), ("data_freshness", "UNKNOWN"),
                             ("pr_required", True), ("source_ids", []),
                             ("scheduled_at", "2026-09-19T09:30:00+09:00"),
                             ("headline", "価格50%減")):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                data = copy.deepcopy(self.data)
                data[field] = value
                result = card.generate_card(data, self.config, Path(temporary))
                self.assertEqual(result["image_status"], "BLOCKED")
                self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_render_failure_is_bounded(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(card.shared, "_font_path", side_effect=RuntimeError("private-secret")):
                result = card.generate_card(self.data, self.config, Path(temporary))
            self.assertEqual(result["reason_codes"], ["IMAGE_RENDER_FAILED"])
            self.assertEqual(result["post_text"], self.data["post_text"])

    def test_candidate_is_created_directly_in_output_and_cleaned(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with card._candidate_file(directory) as candidate:
                self.assertEqual(candidate.parent, directory)
                self.assertTrue(candidate.is_file())
                candidate.write_bytes(b"test")
            self.assertFalse(candidate.exists())

    def test_failed_candidate_is_cleaned(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with self.assertRaises(RuntimeError):
                with card._candidate_file(directory):
                    raise RuntimeError("fixture")
            self.assertEqual(list(directory.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
