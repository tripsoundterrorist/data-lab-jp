import assert from "node:assert/strict";
import { renderAffiliateCtaCandidate } from "../runtime-candidates/affiliate-cta-dom-renderer.mjs";

class Node {
  constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; }
  append(...children) { this.children.push(...children); }
  setAttribute(name, value) { this.attributes[name] = value; }
}
const document = { createElement(tag) { return new Node(tag); } };
const presentation = {
  status: "CTA_READY", cta_visible: true, disclosure_visible: true,
  cta_label: "公式商品ページを見る（外部サイト）",
  disclosure_text: "PR：このリンクはアフィリエイトリンクです。リンク先で購入された場合、DATA LABが報酬を受け取ることがあります。",
  external_indicator_visible: true,
  required_rel_tokens: ["noopener", "noreferrer", "sponsored"],
};
const id = "itm_0123456789abcdef01234567";
const host = new Node("host");
assert.equal(renderAffiliateCtaCandidate(document, host, id, presentation), true);
assert.equal(host.children.length, 1);
const wrapper = host.children[0];
assert.equal(wrapper.children.length, 2);
assert.equal(wrapper.children[0].className, "affiliate-cta-disclosure");
assert.equal(wrapper.children[0].textContent.startsWith("PR："), true);
assert.equal(wrapper.children[1].href, `/go/${id}`);
assert.equal(wrapper.children[1].rel, "noopener noreferrer sponsored");
assert.equal(wrapper.children[1].target, "_blank");

for (const [candidateId, changes] of [
  ["bad", {}], [id, { disclosure_visible: false }],
  [id, { disclosure_text: "" }], [id, { required_rel_tokens: ["noopener"] }],
]) {
  const blockedHost = new Node("host");
  assert.equal(renderAffiliateCtaCandidate(document, blockedHost, candidateId, { ...presentation, ...changes }), false);
  assert.equal(blockedHost.children.length, 0);
}
