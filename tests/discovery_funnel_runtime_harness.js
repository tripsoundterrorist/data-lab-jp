"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs.readFileSync(
  path.resolve(__dirname, "..", "items", "discovery.js"),
  "utf8"
);

function run(withAnalytics) {
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
    ? { dataLabAnalytics: { trackEvent(name) { events.push(name); return true; } } }
    : {};

  vm.runInNewContext(source, { document, window, Set, Array, Number, Date });
  listeners.DOMContentLoaded();
  ctaListeners.click();
  return events;
}

assert.deepStrictEqual(run(true), ["view_item_list", "outbound_product_click"]);
assert.deepStrictEqual(run(false), []);
