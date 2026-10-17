import assert from "node:assert/strict";
import { installArticleNavigationAdapter as install } from "../runtime-candidates/article-navigation-dom-adapter-candidate.mjs";

function scenario() {
  const listeners = new Set();
  const calls = [];
  let consent = null;
  let pathname = "/coupon-help";
  let failRecord = false;
  const root = {
    addEventListener(type, listener, capture) {
      assert.equal(type, "click"); assert.equal(capture, false); listeners.add(listener);
    },
    removeEventListener(type, listener, capture) {
      assert.equal(type, "click"); assert.equal(capture, false); listeners.delete(listener);
    },
    contains(anchor) { return anchor.inside !== false; },
  };
  const getPathname = () => pathname;
  const readConsent = () => consent;
  const record = payload => {
    if (failRecord) throw Error("mock record failure");
    calls.push(payload); return true;
  };
  function anchor(href, attrs = {}) {
    return {
      inside: attrs.inside,
      getAttribute(name) { return name === "href" ? href : (attrs[name] ?? null); },
      hasAttribute(name) { return Object.hasOwn(attrs, name); },
      closest(selector) {
        if (selector === "a[href]") return this;
        if (selector === "article") return attrs.article === false ? null : {};
        throw Error("unexpected selector");
      },
    };
  }
  function click(target = anchor("/column-price"), extra = {}) {
    const event = {
      target, button: 0, defaultPrevented: false,
      preventDefault() { throw Error("navigation blocked"); },
      stopPropagation() { throw Error("propagation blocked"); },
      ...extra,
    };
    const before = {...event};
    for (const listener of listeners) listener(event);
    assert.deepEqual(event, before);
  }
  return {
    root, calls, listeners, anchor, click,
    start: () => install(root, getPathname, readConsent, record),
    consent: value => { consent = value; },
    path: value => { pathname = value; },
    fail: value => { failRecord = value; },
  };
}

const s = scenario();
assert.equal(s.listeners.size, 0);
const cleanup = s.start();
assert.equal(typeof cleanup, "function");
assert.equal(s.calls.length, 0);
assert.equal(s.start(), cleanup);
assert.equal(s.listeners.size, 1);
s.click(); // no consent
s.consent("denied"); s.click();
assert.equal(s.calls.length, 0);
s.consent("granted");
assert.equal(s.calls.length, 0); // no replay
const routes = [
  ["/coupon-help", "/column-price", "coupon_to_price"],
  ["/books-device-check", "/column-price", "device_to_price"],
  ["/column-price", "/items/", "price_to_items"],
];
for (const [from, to, label] of routes) {
  s.path(from); s.click(s.anchor(to));
  assert.deepEqual(s.calls.at(-1), {
    event_name: "article_navigation_click", navigation_route: label,
  });
}
s.path("/coupon-help");
const a = s.anchor("/column-price");
s.click({closest: () => a}); // nested span
s.click({nodeType: 3, parentElement: {closest: () => a}}); // text node
assert.equal(s.calls.length, 5);
for (const extra of [
  {button: 1}, {button: 2}, {defaultPrevented: true},
  {ctrlKey: true}, {metaKey: true}, {shiftKey: true}, {altKey: true},
]) s.click(a, extra);
for (const link of [
  s.anchor("/column-price", {download: ""}),
  s.anchor("/column-price", {target: "_blank"}),
  s.anchor("/column-price", {article: false}),
  s.anchor("/column-price", {inside: false}),
  s.anchor("/column-price?private=value"),
  s.anchor("/column-price#part"),
  s.anchor("https://datalabx.jp/column-price"),
  s.anchor("/go/private"), s.anchor("/"),
]) s.click(link);
s.click(null);
s.click({closest() { throw Error("bad target"); }});
s.path("/coupon-help?private=value"); s.click(a);
assert.equal(s.calls.length, 5);
s.path("/coupon-help");
s.consent("denied"); s.click(a);
s.consent("granted"); s.fail(true); s.click(a); s.fail(false);
assert.equal(s.calls.length, 5);
s.click(s.anchor("/column-price", {target: "_self"}));
assert.equal(s.calls.length, 6);
cleanup(); cleanup();
assert.equal(s.listeners.size, 0);
s.click(a); assert.equal(s.calls.length, 6);
const again = s.start();
assert.notEqual(again, cleanup);
s.click(a); assert.equal(s.calls.length, 7);
again();
assert.equal(install(null, () => "", () => "", () => true), null);
assert.equal(install(s.root, null, () => "", () => true), null);
const t = scenario();
const stop = install(t.root, () => "/coupon-help", () => {throw Error("consent unavailable");}, () => {throw Error("must not record");});
t.click(); stop(); // missing consent fails softly
const broken = {contains() {}, removeEventListener() {}, addEventListener() {throw Error("cannot bind");}};
assert.equal(install(broken, () => "", () => "granted", () => true), null);
