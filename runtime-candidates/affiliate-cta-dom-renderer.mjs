const PUBLIC_ID = /^itm_[0-9a-f]{24}$/u;
const CTA_LABEL = "公式商品ページを見る（外部サイト）";
const DISCLOSURE_TEXT = "PR：このリンクはアフィリエイトリンクです。リンク先で購入された場合、DATA LABが報酬を受け取ることがあります。";
const REL = "noopener noreferrer sponsored";

function validPresentation(value) {
  return value && Object.getPrototypeOf(value) === Object.prototype &&
    Object.keys(value).sort().join(",") === "cta_label,cta_visible,disclosure_text,disclosure_visible,external_indicator_visible,required_rel_tokens,status" &&
    value.status === "CTA_READY" && value.cta_visible === true &&
    value.disclosure_visible === true && value.external_indicator_visible === true &&
    value.cta_label === CTA_LABEL && value.disclosure_text === DISCLOSURE_TEXT &&
    Array.isArray(value.required_rel_tokens) &&
    [...value.required_rel_tokens].sort().join(" ") === "noopener noreferrer sponsored";
}

// Builds one indivisible disclosure + CTA unit. It accepts no external URL;
// only the validated opaque ID becomes a same-origin /go path.
export function renderAffiliateCtaCandidate(document, host, publicId, presentation) {
  try {
    if (!document || typeof document.createElement !== "function" ||
        !host || typeof host.append !== "function" || !PUBLIC_ID.test(publicId) ||
        !validPresentation(presentation)) return false;

    const wrapper = document.createElement("aside");
    wrapper.className = "affiliate-cta-block";
    wrapper.setAttribute("aria-label", "広告リンク");
    const disclosure = document.createElement("p");
    disclosure.className = "affiliate-cta-disclosure";
    disclosure.textContent = DISCLOSURE_TEXT;
    const link = document.createElement("a");
    link.className = "official-link affiliate-cta-link";
    link.textContent = CTA_LABEL;
    link.href = `/go/${publicId}`;
    link.target = "_blank";
    link.rel = REL;
    wrapper.append(disclosure, link);
    host.append(wrapper);
    return true;
  } catch (_) {
    return false;
  }
}

export const AFFILIATE_CTA_DOM_RENDERER_VERSION = "0.1";
