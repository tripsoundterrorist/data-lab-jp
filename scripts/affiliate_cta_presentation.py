"""URL-free presentation contract for a future affiliate CTA."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ui_security_disclosure_policy import (
    AFFILIATE_REL,
    UISecurityResult,
    UI_SECURITY_PASS,
)


PRESENTATION_VERSION = "0.1"
CTA_READY = "CTA_READY"
CTA_HIDDEN = "CTA_HIDDEN"
INVALID_INPUT = "INVALID_INPUT"

CTA_LABEL = "公式商品ページを見る（外部サイト）"
DISCLOSURE_TEXT = (
    "PR：このリンクはアフィリエイトリンクです。"
    "リンク先で購入された場合、DATA LABが報酬を受け取ることがあります。"
)


@dataclass(frozen=True)
class AffiliateCtaPresentation:
    presentation_version: str
    status: str
    cta_visible: bool
    disclosure_visible: bool
    cta_label: str | None
    disclosure_text: str | None
    external_indicator_visible: bool
    required_rel_tokens: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["required_rel_tokens"] = list(self.required_rel_tokens)
        value["reason_codes"] = list(self.reason_codes)
        return value


def _result(
    status: str,
    *,
    visible: bool = False,
    reasons: tuple[str, ...],
) -> AffiliateCtaPresentation:
    return AffiliateCtaPresentation(
        PRESENTATION_VERSION,
        status,
        visible,
        visible,
        CTA_LABEL if visible else None,
        DISCLOSURE_TEXT if visible else None,
        visible,
        tuple(sorted(AFFILIATE_REL)) if visible else (),
        tuple(sorted(set(reasons))),
    )


def build_affiliate_cta(
    *,
    presentation_version: Any,
    ui_security_result: Any,
) -> AffiliateCtaPresentation:
    """Build text and visibility only; never accept or return a link URL."""

    try:
        if presentation_version != PRESENTATION_VERSION:
            return _result(
                INVALID_INPUT, reasons=("UNSUPPORTED_PRESENTATION_VERSION",)
            )
        if not isinstance(ui_security_result, UISecurityResult):
            return _result(
                INVALID_INPUT, reasons=("UI_SECURITY_RESULT_INVALID",)
            )
        if (
            ui_security_result.ui_security_status != UI_SECURITY_PASS
            or ui_security_result.render_allowed is not True
        ):
            return _result(
                CTA_HIDDEN, reasons=("UPSTREAM_UI_SECURITY_BLOCKED",)
            )
        if (
            ui_security_result.disclosure_required is not True
            or ui_security_result.external_indicator_required is not True
            or frozenset(ui_security_result.required_rel_tokens) != AFFILIATE_REL
            or ui_security_result.prohibited_pattern_codes
        ):
            return _result(
                INVALID_INPUT, reasons=("UI_SECURITY_RESULT_CONTRADICTORY",)
            )
        return _result(
            CTA_READY,
            visible=True,
            reasons=("CTA_AND_DISCLOSURE_READY",),
        )
    except Exception:
        return _result(
            INVALID_INPUT, reasons=("AFFILIATE_CTA_PRESENTATION_INTERNAL_ERROR",)
        )


__all__ = [
    "AffiliateCtaPresentation",
    "CTA_HIDDEN",
    "CTA_LABEL",
    "CTA_READY",
    "DISCLOSURE_TEXT",
    "INVALID_INPUT",
    "PRESENTATION_VERSION",
    "build_affiliate_cta",
]
