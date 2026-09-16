"""Deterministic non-posting X card; no network, upload, or scheduler."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

try:
    from . import x_short_video_mvp as shared
except ImportError:
    import x_short_video_mvp as shared

WIDTH, HEIGHT = 1200, 1500
MARGIN = 100


def generate_card(value, config, output_directory: Path, *, font: Path | None = None):
    data, reasons = shared.validate_input(value, config)
    result = {"text_status": "BLOCKED", "image_status": "BLOCKED",
              "post_text": None, "image_path": None, "reason_codes": list(reasons),
              "posting_performed": False, "notification_performed": False,
              "upload_performed": False, "schedule_registered": False}
    if data is None:
        return result
    result.update(text_status="READY", post_text=data["post_text"])
    try:
        selected = shared._font_path(font)
        from PIL import Image, ImageDraw, ImageFont
        image = Image.new("RGB", (WIDTH, HEIGHT), "#071426")
        draw = ImageDraw.Draw(image)
        fonts = {size: ImageFont.truetype(str(selected), size) for size in (30, 36, 48, 68)}
        draw.rectangle((0, 0, WIDTH, 16), fill="#55d6ff")
        draw.text((MARGIN, 85), "DATA LAB", font=fonts[48], fill="#f7fbff")
        draw.text((MARGIN, 165), "FANZA動画｜DATA LABメモ", font=fonts[30], fill="#55d6ff")
        draw.rounded_rectangle((MARGIN, 285, WIDTH-MARGIN, 1125), radius=32,
                               fill="#10243b", outline="#28435e", width=2)

        def block(text, size, y, limit):
            lines = shared._wrap(draw, text, fonts[size], WIDTH-2*MARGIN-90)
            # Avoid a punctuation-only line or Japanese prohibited line start.
            for index in range(1, len(lines)):
                if lines[index][0] in "。、，．！？）】」』":
                    moved = lines[index-1][-1]
                    lines[index-1] = lines[index-1][:-1]
                    lines[index] = moved + lines[index]
            line_height = int(size*1.5)
            if len(lines) > limit:
                raise ValueError("TEXT_OVERFLOW")
            for line in lines:
                box = draw.textbbox((MARGIN+45, y), line, font=fonts[size])
                if box[0] < MARGIN or box[2] > WIDTH-MARGIN or box[3] > 1080:
                    raise ValueError("TEXT_OVERFLOW")
                draw.text((MARGIN+45, y), line, font=fonts[size], fill="#f7fbff")
                y += line_height
            return y

        y = block(data["headline"], 68, 345, 3)
        draw.rectangle((MARGIN+45, y+25, MARGIN+145, y+31), fill="#55d6ff")
        block(data["body_short"], 36, y+90, 5)
        if data["pr_required"]:
            draw.text((MARGIN, 1170), "【PR】", font=fonts[36], fill="#55d6ff")
        draw.text((MARGIN, 1235), "確認済み情報のみ・独自集計・非公式", font=fonts[30], fill="#a9bdce")
        draw.text((MARGIN, 1330), "datalabx.jp", font=fonts[48], fill="#55d6ff")
        output_directory.mkdir(parents=True, exist_ok=True)
        path = output_directory / ("x-card-" + shared._digest(data)[:24] + ".png")
        # Repeat calls return the same immutable candidate, not another notification.
        with tempfile.TemporaryDirectory(prefix="card-", dir=output_directory) as temporary:
            candidate = Path(temporary) / "candidate.png"
            image.save(candidate, format="PNG", optimize=True)
            with Image.open(candidate) as checked:
                checked.verify()
            if candidate.stat().st_size > 5*1024*1024:
                raise ValueError("IMAGE_TOO_LARGE")
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            if path.exists():
                if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    raise ValueError("EXISTING_ARTIFACT_MISMATCH")
            else:
                # Atomically expose a complete artifact without overwrite.
                try:
                    os.link(candidate, path)
                except FileExistsError:
                    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                        raise ValueError("EXISTING_ARTIFACT_MISMATCH")
        result.update(image_status="READY", image_path=str(path), image_sha256=digest,
                      reason_codes=["STATIC_CARD_VALIDATED"])
    except Exception as error:
        safe = str(error)
        result.update(image_status="FAILED", reason_codes=[safe if safe in {
            "TEXT_OVERFLOW", "JAPANESE_FONT_MISSING", "IMAGE_TOO_LARGE",
            "EXISTING_ARTIFACT_MISMATCH"} else "IMAGE_RENDER_FAILED"])
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=shared.DEFAULT_CONFIG)
    parser.add_argument("--output-directory", type=Path, default=shared.ROOT/"runtime/private/x-card-mvp")
    args = parser.parse_args()
    try:
        result = generate_card(shared._load_json(args.input), shared._load_json(args.config), args.output_directory)
    except Exception:
        result = {"text_status": "BLOCKED", "image_status": "BLOCKED", "reason_codes": ["INPUT_READ_FAILED"]}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["image_status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
