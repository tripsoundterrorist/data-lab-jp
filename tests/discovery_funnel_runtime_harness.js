"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs.readFileSync(
  path.resolve(__dirname, "..", "items", "discovery.js"),
  "utf8"
);

function run(withAnalytics, searchParams = "", grantAfterLoad = false) {
  const events = [];
  const listeners = {};
  const ctaListeners = {};
  const imageListeners = {};
  const appended = [];
  const control = (value = "") => ({
    value,
    addEventListener(name, handler) { listeners[`control:${name}`] = handler; },
  });
  const grid = {
    querySelectorAll() { return []; },
    append() {},
  };
  const search = control("");
  const price = control("all");
  const sort = control("original");
  const resultCount = { textContent: "" };
  const pageStatus = { textContent: "" };
  const cta = {
    getAttribute(name) { return name === "href" ? "/go/itm_0123456789abcdef01234567" : null; },
    addEventListener(name, handler) { ctaListeners[name] = handler; },
  };
  const wrapper = { append(value) { appended.push(value); } };
  const image = {
    removed: false,
    addEventListener(name, handler, options) { imageListeners[name] = { handler, options }; },
    closest(selector) { return selector === ".card-image-wrap" ? wrapper : null; },
    remove() { this.removed = true; },
  };
  const document = {
    querySelector(selector) {
      return {
        ".item-grid": grid,
        "#item-search": search,
        "#price-filter": price,
        "#item-sort": sort,
        "#result-count": resultCount,
        "#page-status": pageStatus,
      }[selector] || null;
    },
    querySelectorAll(selector) {
      if (selector === ".affiliate-cta-link") return [cta];
      if (selector === ".card-image") return [image];
      return [];
    },
    createElement(tagName) { return { tagName, className: "", textContent: "" }; },
    addEventListener(name, handler) { listeners[name] = handler; },
  };
  const window = withAnalytics
    ? { location: { search: searchParams }, dataLabAnalytics: { trackEvent(name, context) { events.push({ name, context }); return true; } } }
    : { location: { search: searchParams } };

  vm.runInNewContext(source, { document, window, Set, Array, Number, Date, URLSearchParams });
  listeners.DOMContentLoaded();
  if (grantAfterLoad) {
    window.dataLabAnalytics = { trackEvent(name, context) { events.push({ name, context }); return true; } };
    listeners.dataLabAnalyticsReady();
    listeners.dataLabAnalyticsReady();
  }
  ctaListeners.click();
  imageListeners.error.handler();
  return {
    events,
    price: price.value,
    sort: sort.value,
    imageFallback: appended[0],
    imageRemoved: image.removed,
    imageErrorOnce: imageListeners.error.options.once,
  };
}

const immediate = run(true).events;
assert.strictEqual(immediate.length, 2);
assert.strictEqual(immediate[0].name, "view_item_list");
assert.strictEqual(immediate[0].context, undefined);
assert.strictEqual(immediate[1].name, "outbound_product_click");
assert.strictEqual(immediate[1].context.public_id, "itm_0123456789abcdef01234567");
assert.strictEqual(immediate[1].context.surface, "product_card");
assert.deepStrictEqual(run(false).events, []);
const delayed = run(false, "", true).events;
assert.strictEqual(delayed.length, 2);
assert.strictEqual(delayed[0].name, "view_item_list");
assert.strictEqual(delayed[1].name, "outbound_product_click");
assert.strictEqual(delayed[1].context.public_id, "itm_0123456789abcdef01234567");
assert.strictEqual(delayed[1].context.surface, "product_card");
assert.deepStrictEqual(
  { price: run(false, "?price_band=under-1000&sort=price-asc&utm_source=x").price,
    sort: run(false, "?price_band=under-1000&sort=price-asc&utm_source=x").sort },
  { price: "under-1000", sort: "price-asc" }
);
assert.deepStrictEqual(
  { price: run(false, "?price_band=unsafe&sort=rank").price,
    sort: run(false, "?price_band=unsafe&sort=rank").sort },
  { price: "all", sort: "original" }
);
const fallback = run(false);
assert.equal(fallback.imageRemoved, true);
assert.equal(fallback.imageErrorOnce, true);
assert.equal(fallback.imageFallback.className, "image-placeholder");
assert.equal(fallback.imageFallback.textContent, "画像を取得できませんでした");
