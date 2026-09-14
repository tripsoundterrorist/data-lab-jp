"""Fail-closed, non-posting short-video renderer for DATA LAB X drafts."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "x-short-video-mvp-v0.1.json"
DEFAULT_OUTPUT = ROOT / "runtime" / "private" / "x-video-mvp"
DEFAULT_LEDGER = DEFAULT_OUTPUT / "generation-ledger-v0.1.json"
VERSION = "0.1"
TEMPLATE_ID = "data-lab-vertical-v0.1"
WIDTH = 1080
HEIGHT = 1920
FPS = 30
DURATION_SECONDS = 10.0
MAX_BYTES = 15 * 1024 * 1024
SAFE_MARGIN = 96
JST = timezone(timedelta(hours=9), name="Asia/Tokyo")
ALLOWED_THEMES = frozenset({
    "price_change", "ranking_change", "new_or_updated", "data_literacy",
    "aggregation_transparency", "weekly_summary", "site_update",
})
REQUIRED_FIELDS = frozenset({
    "content_id", "scheduled_at", "timezone", "theme", "headline",
    "body_short", "post_text", "source_ids", "source_checked_at",
    "pr_required", "sensitive_media", "template_id", "data_freshness",
    "generation_status",
})
SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._:-]{0,127}\Z")
NUMBER = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)?%?")
FORBIDDEN_TEXT = re.compile(
    r"(?:残りわずか|今だけ|急げ|絶対|公式ランキング|トレンド予測)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GenerationResult:
    version: str
    status: str
    text_status: str
    video_status: str
    post_text: str | None
    video_path: str | None
    video_sha256: str | None
    duplicate_notification_blocked: bool
    posting_performed: bool
    notification_performed: bool
    schedule_registered: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _timestamp(value: Any, timezone_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("TIMESTAMP_INVALID")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or timezone_name != "Asia/Tokyo":
        raise ValueError("TIMESTAMP_INVALID")
    return parsed.astimezone(JST)


def _load_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        raise ValueError("INPUT_FILE_INVALID")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_input(value: Any, config: Any) -> tuple[dict[str, Any] | None, tuple[str, ...]]:
    reasons: list[str] = []
    if not isinstance(value, Mapping) or set(value) != REQUIRED_FIELDS:
        return None, ("INPUT_SCHEMA_INVALID",)
    if not isinstance(config, Mapping):
        return None, ("SCHEDULE_CONFIG_INVALID",)
    data = dict(value)
    timezone_name = data.get("timezone")
    if timezone_name != config.get("timezone") or timezone_name != "Asia/Tokyo":
        reasons.append("TIMEZONE_INVALID")
    content_id = data.get("content_id")
    if not isinstance(content_id, str) or SAFE_ID.fullmatch(content_id) is None:
        reasons.append("CONTENT_ID_INVALID")
    for field, maximum in (("headline", 34), ("body_short", 72), ("post_text", 140)):
        text = data.get(field)
        if (
            not isinstance(text, str) or not text.strip() or len(text) > maximum
            or any(ord(char) < 32 and char not in "\n\t" for char in text)
            or FORBIDDEN_TEXT.search(text)
        ):
            reasons.append(f"{field.upper()}_INVALID")
    if data.get("theme") not in ALLOWED_THEMES:
        reasons.append("THEME_INVALID")
    if data.get("template_id") != TEMPLATE_ID:
        reasons.append("TEMPLATE_INVALID")
    if data.get("generation_status") != "PENDING":
        reasons.append("GENERATION_STATUS_INVALID")
    if data.get("data_freshness") != "VERIFIED_CURRENT":
        reasons.append("DATA_FRESHNESS_INVALID")
    if type(data.get("pr_required")) is not bool:
        reasons.append("PR_STATE_INVALID")
    elif data["pr_required"] and "【PR】" not in data.get("post_text", ""):
        reasons.append("PR_DISCLOSURE_MISSING")
    if data.get("sensitive_media") is not False:
        reasons.append("SENSITIVE_MEDIA_BLOCKED")
    source_ids = data.get("source_ids")
    if (
        not isinstance(source_ids, list) or not source_ids
        or any(not isinstance(item, str) or SAFE_ID.fullmatch(item) is None for item in source_ids)
        or len(source_ids) != len(set(source_ids))
    ):
        reasons.append("SOURCE_IDS_INVALID")
    try:
        scheduled = _timestamp(data.get("scheduled_at"), timezone_name)
        checked = _timestamp(data.get("source_checked_at"), timezone_name)
        start = datetime.fromisoformat(str(config["test_start"])).date()
        end = datetime.fromisoformat(str(config["test_end"])).date()
        slots = config["slots"]
        day = scheduled.strftime("%A").casefold()
        expected = slots.get(day) if isinstance(slots, Mapping) else None
        if not start <= scheduled.date() <= end:
            reasons.append("TEST_WINDOW_MISMATCH")
        if expected is None:
            reasons.append("NO_POST_DAY")
        elif scheduled.strftime("%H:%M") != expected:
            reasons.append("SCHEDULE_SLOT_MISMATCH")
        age = (scheduled - checked).total_seconds()
        if age < 0 or age > 48 * 60 * 60:
            reasons.append("SOURCE_TIME_INVALID")
    except Exception:
        reasons.append("SCHEDULE_INPUT_INVALID")
    text_numbers = set(NUMBER.findall(f"{data.get('headline', '')} {data.get('body_short', '')}"))
    post_numbers = set(NUMBER.findall(str(data.get("post_text", ""))))
    if not text_numbers.issubset(post_numbers):
        reasons.append("TEXT_VIDEO_NUMBER_MISMATCH")
    if config.get("external_notification_only") is not True:
        reasons.append("EXTERNAL_NOTIFICATION_BOUNDARY_INVALID")
    if config.get("repository_schedule_registration_allowed") is not False:
        reasons.append("SCHEDULE_REGISTRATION_BOUNDARY_INVALID")
    return (data if not reasons else None), tuple(sorted(set(reasons)))


def _digest(data: Mapping[str, Any]) -> str:
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _font_path(explicit: Path | None) -> Path:
    candidates = ([explicit] if explicit else []) + [
        Path("C:/Windows/Fonts/meiryo.ttc"),
        Path("C:/Windows/Fonts/YuGothB.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"),
    ]
    for path in candidates:
        if path is not None and path.is_file() and not path.is_symlink():
            return path
    raise ValueError("JAPANESE_FONT_MISSING")


def _wrap(draw: Any, text: str, font: Any, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            if not current:
                raise ValueError("TEXT_OVERFLOW")
            lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def _draw_text_block(draw: Any, text: str, font: Any, *, y: int, max_lines: int) -> int:
    lines = _wrap(draw, text, font, WIDTH - SAFE_MARGIN * 2)
    if len(lines) > max_lines:
        raise ValueError("TEXT_OVERFLOW")
    line_height = int(font.size * 1.45)
    for line in lines:
        draw.text((SAFE_MARGIN, y), line, font=font, fill="#f7fbff")
        y += line_height
    return y


def _frames(data: Mapping[str, Any], directory: Path, font_path: Path) -> tuple[Path, ...]:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as error:
        raise ValueError("PILLOW_MISSING") from error
    headline_font = ImageFont.truetype(str(font_path), 86)
    body_font = ImageFont.truetype(str(font_path), 54)
    logo_font = ImageFont.truetype(str(font_path), 68)
    small_font = ImageFont.truetype(str(font_path), 40)
    paths: list[Path] = []
    for index in range(3):
        image = Image.new("RGB", (WIDTH, HEIGHT), "#071426")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(
            (SAFE_MARGIN, 170, WIDTH - SAFE_MARGIN, HEIGHT - 190),
            radius=44, fill="#0d2038", outline="#2b8cff", width=4,
        )
        if index == 0:
            draw.text((SAFE_MARGIN, 260), "DATA LAB", font=logo_font, fill="#55d6ff")
            _draw_text_block(draw, str(data["headline"]), headline_font, y=510, max_lines=4)
            draw.text((SAFE_MARGIN, 1510), "確認済みデータから作成", font=small_font, fill="#9fb5ca")
        elif index == 1:
            draw.text((SAFE_MARGIN, 260), "今日のデータメモ", font=small_font, fill="#55d6ff")
            _draw_text_block(draw, str(data["body_short"]), body_font, y=470, max_lines=7)
            for bar, width in enumerate((620, 760, 520)):
                top = 1240 + bar * 105
                draw.rounded_rectangle((SAFE_MARGIN, top, SAFE_MARGIN + width, top + 42), radius=21, fill="#2b8cff")
        else:
            draw.text((SAFE_MARGIN, 570), "DATA LAB", font=logo_font, fill="#55d6ff")
            draw.text((SAFE_MARGIN, 760), "FANZA動画をデータで見る", font=body_font, fill="#f7fbff")
            draw.text((SAFE_MARGIN, 1010), "datalabx.jp", font=logo_font, fill="#2b8cff")
            draw.text((SAFE_MARGIN, 1420), "独自集計・非公式", font=small_font, fill="#9fb5ca")
        path = directory / f"frame-{index}.png"
        image.save(path, format="PNG", optimize=True)
        paths.append(path)
    return tuple(paths)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)


def _render(
    data: Mapping[str, Any], output: Path, *, ffmpeg: str, ffprobe: str,
    font: Path | None,
) -> tuple[str, tuple[str, ...]]:
    ffmpeg_path = shutil.which(ffmpeg) if not Path(ffmpeg).is_file() else ffmpeg
    ffprobe_path = shutil.which(ffprobe) if not Path(ffprobe).is_file() else ffprobe
    if not ffmpeg_path or not ffprobe_path:
        raise ValueError("FFMPEG_NOT_AVAILABLE")
    selected_font = _font_path(font)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary = Path(temporary_directory)
        frames = _frames(data, temporary, selected_font)
        concat = temporary / "frames.txt"
        concat.write_text(
            "".join(
                f"file '{path.as_posix()}'\nduration {duration}\n"
                for path, duration in zip(frames, (2, 6, 2))
            ) + f"file '{frames[-1].as_posix()}'\n",
            encoding="utf-8",
        )
        candidate_output = temporary / "candidate.mp4"
        command = [
            str(ffmpeg_path), "-y", "-v", "error", "-f", "concat", "-safe", "0",
            "-i", str(concat), "-vf",
            "fps=30,fade=t=in:st=0:d=0.3,fade=t=out:st=9.7:d=0.3,format=yuv420p",
            "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "24",
            "-threads", "1", "-map_metadata", "-1", "-movflags", "+faststart",
            "-t", str(DURATION_SECONDS),
            str(candidate_output),
        ]
        rendered = _run(command)
        if rendered.returncode != 0 or not candidate_output.is_file():
            raise ValueError("VIDEO_RENDER_FAILED")
        probed = _run([
            str(ffprobe_path), "-v", "error", "-show_streams", "-show_format",
            "-of", "json", str(candidate_output),
        ])
        if probed.returncode != 0:
            raise ValueError("VIDEO_PROBE_FAILED")
        metadata = json.loads(probed.stdout)
        streams = metadata.get("streams", [])
        videos = [item for item in streams if item.get("codec_type") == "video"]
        audios = [item for item in streams if item.get("codec_type") == "audio"]
        duration = float(metadata.get("format", {}).get("duration", 0))
        valid = (
            len(videos) == 1 and not audios
            and videos[0].get("codec_name") == "h264"
            and videos[0].get("width") == WIDTH and videos[0].get("height") == HEIGHT
            and videos[0].get("r_frame_rate") == "30/1"
            and 8.0 <= duration <= 12.0
            and 0 < candidate_output.stat().st_size <= MAX_BYTES
        )
        if not valid:
            raise ValueError("VIDEO_SPEC_INVALID")
        os.replace(candidate_output, output)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return digest, ("VIDEO_SPEC_VERIFIED", "NO_AUDIO_VERIFIED")


def _ledger(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": VERSION, "records": {}}
    if path.is_symlink() or not path.is_file():
        raise ValueError("LEDGER_INVALID")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("version") != VERSION or not isinstance(value.get("records"), dict):
        raise ValueError("LEDGER_INVALID")
    return value


def _save_ledger(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def generate(
    value: Any,
    config: Any,
    *,
    output_directory: Path = DEFAULT_OUTPUT,
    ledger_path: Path = DEFAULT_LEDGER,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
    font: Path | None = None,
) -> GenerationResult:
    data, reasons = validate_input(value, config)
    if data is None:
        return GenerationResult(
            VERSION, "BLOCKED", "BLOCKED", "NOT_ATTEMPTED", None, None, None,
            False, False, False, False, reasons,
        )
    post_text = str(data["post_text"])
    lock: Path | None = None
    rendered_output: Path | None = None
    try:
        if output_directory.is_symlink() or ledger_path.is_symlink():
            raise ValueError("OUTPUT_PATH_INVALID")
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        if ledger_path.parent.is_symlink():
            raise ValueError("OUTPUT_PATH_INVALID")
        lock = ledger_path.with_name(ledger_path.name + ".lock")
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
        except FileExistsError as error:
            lock = None
            raise ValueError("GENERATION_ALREADY_RUNNING") from error
        ledger = _ledger(ledger_path)
        key = hashlib.sha256(str(data["content_id"]).encode("utf-8")).hexdigest()
        input_digest = _digest(data)
        existing = ledger["records"].get(key)
        if existing is not None:
            same = isinstance(existing, Mapping) and existing.get("input_sha256") == input_digest
            return GenerationResult(
                VERSION, "TEXT_READY_VIDEO_ALREADY_GENERATED" if same else "BLOCKED",
                "READY" if same else "BLOCKED", "ALREADY_GENERATED" if same else "NOT_ATTEMPTED",
                post_text if same else None, existing.get("video_path") if same else None,
                existing.get("video_sha256") if same else None, True, False, False, False,
                ("DUPLICATE_NOTIFICATION_BLOCKED",) if same else ("CONTENT_ID_REUSE_BLOCKED",),
            )
        filename = f"x-video-{key[:12]}-{input_digest[:12]}.mp4"
        output = output_directory / filename
        video_sha, render_reasons = _render(
            data, output, ffmpeg=ffmpeg, ffprobe=ffprobe, font=font
        )
        rendered_output = output
        ledger["records"][key] = {
            "input_sha256": input_digest,
            "video_sha256": video_sha,
            "video_path": str(output.resolve()),
            "scheduled_at": data["scheduled_at"],
            "notification_status": "PENDING_MANUAL_DELIVERY",
        }
        _save_ledger(ledger_path, ledger)
        rendered_output = None
        return GenerationResult(
            VERSION, "TEXT_AND_VIDEO_READY", "READY", "READY", post_text,
            str(output.resolve()), video_sha, False, False, False, False,
            render_reasons + ("MANUAL_POST_ONLY",),
        )
    except Exception as error:
        if rendered_output is not None and rendered_output.is_file():
            try:
                rendered_output.unlink()
            except OSError:
                pass
        code = str(error)
        safe_code = code if re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", code) else "VIDEO_GENERATION_FAILED"
        return GenerationResult(
            VERSION, "TEXT_READY_VIDEO_FAILED", "READY", "FAILED", post_text,
            None, None, False, False, False, False, (safe_code,),
        )
    finally:
        if lock is not None and lock.is_file():
            try:
                lock.unlink()
            except OSError:
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--font", type=Path)
    args = parser.parse_args(argv)
    try:
        result = generate(
            _load_json(args.input), _load_json(args.config),
            output_directory=args.output_directory, ledger_path=args.ledger,
            ffmpeg=args.ffmpeg, ffprobe=args.ffprobe, font=args.font,
        )
    except Exception:
        result = GenerationResult(
            VERSION, "BLOCKED", "BLOCKED", "NOT_ATTEMPTED", None, None, None,
            False, False, False, False, ("INPUT_LOAD_FAILED",),
        )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.text_status == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
