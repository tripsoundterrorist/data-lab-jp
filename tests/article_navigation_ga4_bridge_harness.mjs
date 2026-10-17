import assert from "node:assert/strict";
import { createArticleNavigationRecorder as create } from "../runtime-candidates/article-navigation-ga4-bridge-candidate.mjs";
import { installArticleNavigationAdapter as install } from "../runtime-candidates/article-navigation-dom-adapter-candidate.mjs";

const calls = [];
let consent = null;
const read = () => consent;
const recorder = create(read, (...args) => calls.push(args));
const valid = {event_name: "article_navigation_click", navigation_route: "coupon_to_price"};
for (const choice of [null, undefined, "denied", "", true, "GRANTED"]) {
  consent = choice;
  assert.equal(recorder(valid), false);
}
assert.equal(calls.length, 0);
consent = "granted";
assert.equal(calls.length, 0); // no delayed replay
for (const [label, path] of [
  ["coupon_to_price", "/coupon-help"],
  ["device_to_price", "/books-device-check"],
  ["price_to_items", "/column-price"],
]) {
  assert.equal(recorder({event_name: "article_navigation_click", navigation_route: label}), true);
  const [command, event, params] = calls.at(-1);
  assert.equal(command, "event");
  assert.equal(event, "article_navigation_click");
  assert.deepEqual(params, {
    navigation_route: label, page_location: "https://datalabx.jp" + path,
    page_path: path, page_referrer: "",
  });
  assert(Object.isFrozen(params));
}
for (const bad of [
  null, [], {}, {...valid, user_id: "private"}, {...valid, item_id: "private"},
  {...valid, page_location: "https://example.test/?private=value"},
  {...valid, page_referrer: "private"}, {...valid, [Symbol("extra")]: true},
  {...valid, event_name: "outbound_product_click"},
  {...valid, navigation_route: "__proto__"}, {...valid, navigation_route: "unknown"},
]) assert.equal(recorder(bad), false);
assert.equal(calls.length, 3);
consent = "denied"; assert.equal(recorder(valid), false);
assert.equal(calls.length, 3);
consent = "granted";
assert.equal(create(() => {throw Error("consent failed");}, () => {throw Error("must not call");})(valid), false);
assert.equal(create(read, () => {throw Error("mock invocation failed");})(valid), false);
assert.equal(create(null, () => {})(valid), false);
assert.equal(create(read, null)(valid), false);
assert.equal(recorder(new Proxy({}, {ownKeys() {throw Error("bad input");}})), false);
assert.equal(calls.length, 3);

// Composition: mock DOM -> existing observer -> consent recheck -> mock invocation.
const listeners = new Set();
const root = {
  contains: () => true,
  addEventListener: (type, callback) => {assert.equal(type, "click"); listeners.add(callback);},
  removeEventListener: (type, callback) => {assert.equal(type, "click"); listeners.delete(callback);},
};
const link = {
  closest: selector => selector === "a[href]" ? link : {},
  hasAttribute: () => false,
  getAttribute: name => name === "href" ? "/column-price" : null,
};
const click = () => {for (const callback of listeners) callback({button: 0, target: link});};
const cleanup = install(root, () => "/coupon-help", read, recorder);
assert.equal(calls.length, 3); // installing never records
assert.equal(install(root, () => "/coupon-help", read, recorder), cleanup);
click(); assert.equal(calls.length, 4);
consent = "denied"; click(); assert.equal(calls.length, 4);
consent = "granted"; assert.equal(calls.length, 4);
click(); assert.equal(calls.length, 5);
cleanup(); click(); assert.equal(calls.length, 5);

// Consent may change between observation and invocation; the bridge checks again.
let reads = 0;
const changingConsent = () => ++reads === 1 ? "granted" : "denied";
const blocked = create(changingConsent, () => {throw Error("must not invoke");});
const stop = install(root, () => "/coupon-help", changingConsent, blocked);
click(); assert.equal(reads, 2); stop();
