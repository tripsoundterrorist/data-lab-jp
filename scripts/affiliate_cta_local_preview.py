"""Generate an isolated local preview of the guarded affiliate CTA."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
from html import escape
import json
from pathlib import Path
import tempfile
from typing import Any

import affiliate_cta_presentation as cta
import ui_security_disclosure_policy as ui_policy


PREVIEW_VERSION = "0.1"
LOCAL_PREVIEW_READY = "LOCAL_PREVIEW_READY"
FAIL_CLOSED = "FAIL_CLOSED"
DUMMY_URL = "https://example.invalid/affiliate-preview"


@dataclass(frozen=True)
class AffiliateCtaLocalPreviewResult:
    preview_version: str
    status: str
    local_preview_only: bool
    dummy_url_only: bool
    blocked_fixture_hidden: bool
    output_file_count: int
    production_write_performed: bool
    publication_allowed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _passing_security_result() -> ui_policy.UISecurityResult:
    return ui_policy.UISecurityResult(
        policy_version=ui_policy.POLICY_VERSION,
        ui_security_status=ui_policy.UI_SECURITY_PASS,
        render_allowed=True,
        disclosure_required=True,
        external_indicator_required=True,
        required_rel_tokens=tuple(sorted(ui_policy.AFFILIATE_REL)),
        prohibited_pattern_codes=(),
        reason_codes=("UI_SECURITY_REQUIREMENTS_SATISFIED",),
    )


def _safe_new_output(path: Path) -> Path:
    resolved = path.resolve()
    temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
    resolved.relative_to(temp_root)
    if resolved == temp_root or resolved.exists() or resolved.parent.is_symlink():
        raise ValueError("output must be a new directory under the temp root")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _render_document(presentation: cta.AffiliateCtaPresentation) -> str:
    rel = " ".join(presentation.required_rel_tokens)
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>アフィリエイトCTA ローカルプレビュー | DATA LAB</title>
  <style>
    :root {{ color-scheme: dark; font-family: system-ui, sans-serif; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; min-height: 100vh; background: #090d18; color: #f5f7ff; }}
    main {{ width: min(720px, 100%); margin: 0 auto; padding: 48px 24px; }}
    .notice {{ color: #ffe69a; font-weight: 800; letter-spacing: .04em; }}
    .panel {{ margin-top: 24px; padding: 28px; border: 1px solid #4a5574;
      border-radius: 18px; background: #12192b; box-shadow: 0 16px 42px #0006; }}
    .label {{ color: #9eadd5; font-size: .82rem; letter-spacing: .14em; }}
    h1 {{ font-size: clamp(1.55rem, 5vw, 2.35rem); line-height: 1.25; }}
    .disclosure {{ margin: 24px 0 12px; padding: 14px 16px; border-left: 4px solid #ffd75e;
      background: #202438; font-weight: 700; line-height: 1.65; }}
    .cta {{ display: inline-flex; align-items: center; justify-content: center; width: 100%;
      min-height: 52px; padding: 12px 18px; border-radius: 12px; background: #fff;
      color: #11182a; font-weight: 900; text-decoration: none; text-align: center; }}
    .cta:focus-visible {{ outline: 3px solid #ffd75e; outline-offset: 4px; }}
    .note {{ color: #b9c3df; line-height: 1.7; }}
    @media (max-width: 430px) {{
      main {{ padding: 24px 14px; }}
      .panel {{ padding: 20px 16px; border-radius: 14px; }}
      .cta {{ min-height: 48px; }}
    }}
  </style>
</head>
<body>
  <main>
    <p class="notice">ローカルプレビュー（非公開・ダミーリンク）</p>
    <section class="panel" aria-labelledby="preview-title">
      <p class="label">AFFILIATE CTA REVIEW</p>
      <h1 id="preview-title">商品ページへの安全な送客表示</h1>
      <p class="note">実商品・実アフィリエイトURL・販売可否は使用していません。</p>
      <p class="disclosure">{escape(presentation.disclosure_text or "")}</p>
      <a class="cta" href="{DUMMY_URL}" target="_blank" rel="{escape(rel)}">{escape(presentation.cta_label or "")}</a>
      <p class="note">このリンクは表示確認専用です。リンク先が開かないことが正常です。</p>
    </section>
  </main>
</body>
</html>
"""


def build_preview(output_directory: Path) -> AffiliateCtaLocalPreviewResult:
    """Build one local-only HTML file; never deploy or use a real URL."""

    try:
        output = _safe_new_output(output_directory)
        allowed = cta.build_affiliate_cta(
            presentation_version=cta.PRESENTATION_VERSION,
            ui_security_result=_passing_security_result(),
        )
        blocked = cta.build_affiliate_cta(
            presentation_version=cta.PRESENTATION_VERSION,
            ui_security_result=replace(
                _passing_security_result(),
                ui_security_status=ui_policy.BLOCKED_UPSTREAM,
                render_allowed=False,
            ),
        )
        blocked_hidden = (
            blocked.status == cta.CTA_HIDDEN
            and blocked.cta_visible is False
            and blocked.disclosure_visible is False
            and blocked.cta_label is None
            and blocked.disclosure_text is None
        )
        if allowed.status != cta.CTA_READY or not blocked_hidden:
            raise ValueError("presentation fixtures invalid")

        document = _render_document(allowed)
        required = (
            'name="robots" content="noindex,nofollow"',
            "ローカルプレビュー（非公開・ダミーリンク）",
            DUMMY_URL,
            "PR：",
            "アフィリエイトリンク",
            'rel="noopener noreferrer sponsored"',
            "@media (max-width: 430px)",
            "min-height: 48px",
        )
        if any(marker not in document for marker in required):
            raise ValueError("preview validation failed")
        output.mkdir()
        (output / "index.html").write_text(document, encoding="utf-8", newline="\n")
        return AffiliateCtaLocalPreviewResult(
            PREVIEW_VERSION,
            LOCAL_PREVIEW_READY,
            True,
            True,
            True,
            1,
            False,
            False,
            ("LOCAL_AFFILIATE_CTA_PREVIEW_READY",),
        )
    except Exception:
        return AffiliateCtaLocalPreviewResult(
            PREVIEW_VERSION,
            FAIL_CLOSED,
            True,
            True,
            False,
            0,
            False,
            False,
            ("LOCAL_AFFILIATE_CTA_PREVIEW_ERROR",),
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build an isolated local-only affiliate CTA preview."
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = build_preview(args.output)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if result.status == LOCAL_PREVIEW_READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
