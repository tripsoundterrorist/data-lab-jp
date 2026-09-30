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
    addEventListener(name, handler) { ctaListeners[name] = handler; },
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
      return selector === ".affiliate-cta-link" ? [cta] : [];
    },
    addEventListener(name, handler) { listeners[name] = handler; },
  };
  const window = withAnalytics
    ? { location: { search: searchParams }, dataLabAnalytics: { trackEvent(name) { events.push(name); return true; } } }
    : { location: { search: searchParams } };

  vm.runInNewContext(source, { document, window, Set, Array, Number, Date, URLSearchParams });
  listeners.DOMContentLoaded();
  if (grantAfterLoad) {
    window.dataLabAnalytics = { trackEvent(name) { events.push(name); return true; } };
    listeners.dataLabAnalyticsReady();
    listeners.dataLabAnalyticsReady();
  }
  ctaListeners.click();
  return { events, price: price.value, sort: sort.value };
}

assert.deepStrictEqual(run(true).events, ["view_item_list", "outbound_product_click"]);
assert.deepStrictEqual(run(false).events, []);
assert.deepStrictEqual(
  run(false, "", true).events,
  ["view_item_list", "outbound_product_click"]
);
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
