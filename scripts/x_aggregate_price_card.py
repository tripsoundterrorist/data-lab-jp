"""Render a deterministic, non-distributable aggregate price card preview."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from . import x_aggregate_marketing_candidate as gate
    from . import x_short_video_mvp as shared
except ImportError:
    import x_aggregate_marketing_candidate as gate
    import x_short_video_mvp as shared


WIDTH, HEIGHT = 1200, 1500
REQUIRED_FACTS = {
    "item_count",
    "under_1000",
    "from_1000_to_1999",
    "from_2000_to_2999",
    "median_yen",
}


def render_price_card(
    value: Any,
    output_path: Path,
    *,
    font: Path | None = None,
) -> dict[str, Any]:
    result = {
        "status": "BLOCKED",
        "image_path": None,
        "image_sha256": None,
        "compliance_review_required": True,
        "distribution_allowed": False,
        "posting_performed": False,
        "upload_performed": False,
        "reason_codes": [],
    }
    if not isinstance(value, dict):
        result["reason_codes"] = ["INPUT_INVALID"]
        return result
    candidate = gate.build_candidate(
        fact_text=value.get("candidate_text"),
        theme=value.get("theme"),
        source_type=value.get("source_type"),
        source_ids=value.get("source_ids"),
        source_checked_at=value.get("source_checked_at"),
        aggregate_facts=value.get("aggregate_facts"),
    )
    if candidate.status != gate.READY_FOR_COMPLIANCE_REVIEW:
        result["reason_codes"] = list(candidate.reason_codes)
        return result
    facts = candidate.aggregate_facts
    if set(facts) != REQUIRED_FACTS or any(type(facts[key]) is not int for key in REQUIRED_FACTS):
        result["reason_codes"] = ["PRICE_FACT_SCHEMA_INVALID"]
        return result
    buckets = [facts["under_1000"], facts["from_1000_to_1999"], facts["from_2000_to_2999"]]
    if sum(buckets) != facts["item_count"] or facts["item_count"] <= 0:
        result["reason_codes"] = ["PRICE_BUCKET_TOTAL_MISMATCH"]
        return result
    try:
        from PIL import Image, ImageDraw, ImageFont

        selected = shared._font_path(font)
        image = Image.new("RGB", (WIDTH, HEIGHT), "#071426")
        draw = ImageDraw.Draw(image)
        fonts = {
            size: ImageFont.truetype(str(selected), size)
            for size in (26, 30, 36, 42, 48, 64, 88, 132)
        }
        # Pure black base keeps the data colors crisp in the X timeline.
        draw.rectangle((0, 0, WIDTH, HEIGHT), fill="#000000")
        for x in range(70, WIDTH, 80):
            for y_dot in range(55, HEIGHT, 80):
                draw.ellipse((x, y_dot, x + 3, y_dot + 3), fill="#173044")

        draw.rounded_rectangle((70, 55, 1130, 220), radius=34, fill="#0d263e")
        draw.text((110, 96), "DATA LAB", font=fonts[48], fill="#f7fbff")
        draw.rounded_rectangle((760, 92, 1090, 178), radius=43, fill="#143d59")
        draw.text((808, 116), "PRICE SNAPSHOT", font=fonts[26], fill="#5bdbff")

        draw.text((72, 282), "公開中", font=fonts[42], fill="#80e7ff")
        draw.text((70, 338), "100", font=fonts[132], fill="#f7fbff")
        draw.text((340, 415), "作品の価格分布", font=fonts[64], fill="#f7fbff")
        draw.text((75, 515), "FANZA動画  /  公開ページ集計", font=fonts[30], fill="#9fb8ca")
        draw.line((75, 575, 1125, 575), fill="#24455f", width=2)

        labels = ("1,000円未満", "1,000〜1,999円", "2,000〜2,999円")
        colors = ("#52d6ff", "#7b8dff", "#35e0b5")
        maximum = max(buckets)
        y = 635
        for label, count, color in zip(labels, buckets, colors):
            percentage = round(count * 100 / facts["item_count"])
            draw.text((75, y), label, font=fonts[36], fill="#dce8f2")
            count_text = f"{count}作品"
            count_box = draw.textbbox((0, 0), count_text, font=fonts[42])
            draw.text((1125 - (count_box[2] - count_box[0]), y - 4), count_text, font=fonts[42], fill="#f7fbff")
            draw.rounded_rectangle((75, y + 65, 1125, y + 133), radius=28, fill="#132f49")
            width = max(68, round(1050 * count / maximum))
            draw.rounded_rectangle((75, y + 65, 75 + width, y + 133), radius=28, fill=color)
            draw.text((88, y + 81), f"{percentage}%", font=fonts[26], fill="#071426")
            y += 185

        draw.rounded_rectangle((70, 1208, 1130, 1370), radius=36, fill="#102e48", outline="#31536d", width=2)
        draw.text((115, 1240), "価格中央値", font=fonts[30], fill="#9fb8ca")
        draw.text((395, 1225), f"{facts['median_yen']:,}円", font=fonts[64], fill="#f7fbff")
        checked = datetime.fromisoformat(candidate.source_checked_at.replace("Z", "+00:00"))
        checked_label = checked.strftime("%Y/%m/%d %H:%M %z")
        draw.text((75, 1420), f"DATA CHECKED  {checked_label}", font=fonts[26], fill="#7895aa")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, format="PNG", optimize=True)
        with Image.open(output_path) as checked:
            checked.verify()
        if output_path.stat().st_size > 5 * 1024 * 1024:
            output_path.unlink(missing_ok=True)
            raise ValueError("IMAGE_TOO_LARGE")
        digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
    except Exception as error:
        output_path.unlink(missing_ok=True)
        safe = str(error)
        result["reason_codes"] = [
            safe if safe in {"JAPANESE_FONT_MISSING", "IMAGE_TOO_LARGE"} else "IMAGE_RENDER_FAILED"
        ]
        return result
    result.update(
        status="READY_FOR_COMPLIANCE_REVIEW",
        image_path=str(output_path),
        image_sha256=digest,
        reason_codes=["COMPLIANCE_REVIEW_REQUIRED"],
    )
    return result


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        value = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        result = {"status": "BLOCKED", "reason_codes": ["INPUT_READ_FAILED"]}
    else:
        result = render_price_card(value, args.output)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "READY_FOR_COMPLIANCE_REVIEW" else 2


if __name__ == "__main__":
    raise SystemExit(main())
