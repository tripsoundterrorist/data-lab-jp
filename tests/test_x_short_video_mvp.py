from copy import deepcopy
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import x_short_video_mvp as video  # noqa: E402


CONFIG = json.loads(
    (ROOT / "config" / "x-short-video-mvp-v0.1.json").read_text(encoding="utf-8")
)
SAFE = json.loads(
    (ROOT / "tests" / "fixtures" / "x-short-video-safe-v0.1.json").read_text(
        encoding="utf-8"
    )
)


class XShortVideoMvpTests(unittest.TestCase):
    def validate(self, **changes):
        value = deepcopy(SAFE)
        value.update(changes)
        return video.validate_input(value, CONFIG)

    def test_safe_input_and_external_schedule(self):
        data, reasons = self.validate()
        self.assertIsNotNone(data)
        self.assertEqual(reasons, ())
        self.assertTrue(CONFIG["external_notification_only"])
        self.assertFalse(CONFIG["repository_schedule_registration_allowed"])

    def test_saturday_and_wrong_slots_are_blocked(self):
        for scheduled, reason in (
            ("2026-09-19T12:30:00+09:00", "NO_POST_DAY"),
            ("2026-09-15T09:30:00+09:00", "SCHEDULE_SLOT_MISMATCH"),
            ("2026-09-16T12:30:00+09:00", "SCHEDULE_SLOT_MISMATCH"),
        ):
            with self.subTest(scheduled=scheduled):
                _, reasons = self.validate(scheduled_at=scheduled)
                self.assertIn(reason, reasons)

    def test_pr_length_media_freshness_and_number_gates(self):
        cases = (
            ({"pr_required": True}, "PR_DISCLOSURE_MISSING"),
            ({"post_text": "あ" * 141}, "POST_TEXT_INVALID"),
            ({"sensitive_media": True}, "SENSITIVE_MEDIA_BLOCKED"),
            ({"data_freshness": "UNKNOWN"}, "DATA_FRESHNESS_INVALID"),
            ({"headline": "価格が20%変化"}, "TEXT_VIDEO_NUMBER_MISMATCH"),
        )
        for changes, reason in cases:
            with self.subTest(reason=reason):
                _, reasons = self.validate(**changes)
                self.assertIn(reason, reasons)

    def test_long_japanese_headline_is_rejected(self):
        _, reasons = self.validate(headline="長" * 35)
        self.assertIn("HEADLINE_INVALID", reasons)

    def test_video_failure_preserves_text_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = video.generate(
                SAFE, CONFIG, output_directory=root / "out", ledger_path=root / "ledger.json",
                ffmpeg="missing-ffmpeg", ffprobe="missing-ffprobe",
            )
        self.assertEqual(result.status, "TEXT_READY_VIDEO_FAILED")
        self.assertEqual(result.text_status, "READY")
        self.assertEqual(result.video_status, "FAILED")
        self.assertEqual(result.post_text, SAFE["post_text"])
        self.assertFalse(result.notification_performed)
        self.assertFalse(result.posting_performed)

    def test_success_records_once_and_blocks_duplicate_notification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "out" / "candidate.mp4"

            def render(_data, path, **_kwargs):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"fixture-mp4")
                return "a" * 64, ("VIDEO_SPEC_VERIFIED",)

            with mock.patch.object(video, "_render", side_effect=render):
                first = video.generate(SAFE, CONFIG, output_directory=root / "out", ledger_path=root / "ledger.json")
                second = video.generate(SAFE, CONFIG, output_directory=root / "out", ledger_path=root / "ledger.json")
        self.assertEqual(first.status, "TEXT_AND_VIDEO_READY")
        self.assertEqual(second.status, "TEXT_READY_VIDEO_ALREADY_GENERATED")
        self.assertTrue(second.duplicate_notification_blocked)
        self.assertFalse(second.notification_performed)

    def test_content_id_reuse_with_changed_input_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(video, "_render", return_value=("b" * 64, ("VIDEO_SPEC_VERIFIED",))):
                first = video.generate(SAFE, CONFIG, output_directory=root, ledger_path=root / "ledger.json")
            changed = deepcopy(SAFE)
            changed["post_text"] += "更新"
            second = video.generate(changed, CONFIG, output_directory=root, ledger_path=root / "ledger.json")
        self.assertEqual(first.text_status, "READY")
        self.assertEqual(second.status, "BLOCKED")
        self.assertIn("CONTENT_ID_REUSE_BLOCKED", second.reason_codes)

    def test_concurrent_generation_lock_preserves_text_and_blocks_video(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "ledger.json"
            lock = root / "ledger.json.lock"
            lock.write_text("held", encoding="utf-8")
            result = video.generate(
                SAFE, CONFIG, output_directory=root / "out", ledger_path=ledger
            )
            self.assertTrue(lock.exists())
        self.assertEqual(result.status, "TEXT_READY_VIDEO_FAILED")
        self.assertEqual(result.text_status, "READY")
        self.assertIn("GENERATION_ALREADY_RUNNING", result.reason_codes)

    def test_ledger_failure_removes_completed_but_untracked_video(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            created = None

            def render(_data, path, **_kwargs):
                nonlocal created
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"complete-but-untracked")
                created = path
                return "c" * 64, ("VIDEO_SPEC_VERIFIED",)

            with (
                mock.patch.object(video, "_render", side_effect=render),
                mock.patch.object(video, "_save_ledger", side_effect=OSError("private")),
            ):
                result = video.generate(
                    SAFE, CONFIG, output_directory=root / "out",
                    ledger_path=root / "ledger.json",
                )
            self.assertIsNotNone(created)
            self.assertFalse(created.exists())
        self.assertEqual(result.status, "TEXT_READY_VIDEO_FAILED")
        self.assertNotIn("private", json.dumps(result.to_dict()))

    def test_renderer_contract_is_vertical_silent_and_bounded(self):
        source = (ROOT / "scripts" / "x_short_video_mvp.py").read_text(
            encoding="utf-8"
        )
        for value in ('WIDTH = 1080', 'HEIGHT = 1920', 'FPS = 30', '"-an"',
                      '"libx264"', '8.0 <= duration <= 12.0', 'MAX_BYTES',
                      '"-t", str(DURATION_SECONDS)'):
            self.assertIn(value, source)
        for forbidden in ("DMM_API_ID", "DMM_AFFILIATE_ID", "x.com/compose", "requests.post"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
