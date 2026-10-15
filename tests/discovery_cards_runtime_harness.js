"use strict";

// Synthetic cards only: no product data, browser, network, or analytics sends.
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const source = fs.readFileSync(path.resolve(__dirname, "..", "items", "discovery.js"), "utf8");

function setup({ mode = "absent", href = "/go/itm_0123456789abcdef01234567", params = "" } = {}) {
  const events = [];
  const listeners = {};
  const control = (value) => ({ value, handlers: {}, addEventListener(n, f) { this.handlers[n] = f; } });
  const search = control("");
  const price = control("all");
  const sort = control("original");
  const rows = [
    ["A", "Alpha", "999\u5186\u301c", "2026-10-12T00:00:00Z"],
    ["B", "Beta", "1,000\u5186\u301c", "2026-10-11T00:00:00Z"],
    ["C", "Gamma", "1,999\u5186\u301c", "2026-10-10T00:00:00Z"],
    ["D", "Delta", "2,000\u5186\u301c", "2026-10-09T00:00:00Z"],
    ["E", "Epsilon", "2,999\u5186\u301c", "2026-10-08T00:00:00Z"],
    ["F", "Zeta", "3,000\u5186\u301c", "2026-10-07T00:00:00Z"],
    ["G", "Alpha tie", "999\u5186\u301c", "2026-10-12T00:00:00Z"],
  ];
  const cards = rows.map(([id, title, amount, time]) => ({
    id, hidden: false,
    querySelector(s) {
      const values = { h2: title, ".price": amount, time };
      return Object.hasOwn(values, s) ? { textContent: values[s] } : null;
    },
  }));
  const order = [...cards];
  const grid = {
    querySelectorAll(selector) {
      assert.strictEqual(selector, ":scope > .item");
      return [...cards];
    },
    append(card) {
      const index = order.indexOf(card);
      assert.notStrictEqual(index, -1);
      order.splice(index, 1); order.push(card);
    },
  };
  const resultCount = { textContent: "" };
  const pageStatus = { textContent: "" };
  const cta = {
    handlers: {},
    getAttribute(name) { return name === "href" ? href : null; },
    addEventListener(n, f) { this.handlers[n] = f; },
  };
  const controls = { ".item-grid": grid, "#item-search": search, "#price-filter": price,
    "#item-sort": sort, "#result-count": resultCount, "#page-status": pageStatus };
  const document = {
    querySelector(s) { return controls[s] || null; },
    querySelectorAll(s) { return s === ".affiliate-cta-link" ? [cta] : []; },
    addEventListener(n, f) { listeners[n] = f; },
  };
  const window = { location: { search: params } };
  if (mode !== "absent") window.dataLabAnalytics = { trackEvent(name, context) {
    if (mode === "throws") throw new Error("synthetic receiver failure");
    if (mode === "denied") return false;
    events.push({ name, context }); return true;
  } };
  vm.runInNewContext(source, { document, window, Set, Array, Number, Date, URLSearchParams });
  listeners.DOMContentLoaded();
  return {
    events, listeners, resultCount, pageStatus,
    visible() { return order.filter(c => !c.hidden).map(c => c.id); },
    change(key, value) {
      const c = { search, price, sort }[key]; c.value = value;
      c.handlers[key === "search" ? "input" : "change"]();
    },
    click() {
      const event = { prevented: false, preventDefault() { this.prevented = true; } };
      cta.handlers.click(event); return event.prevented;
    },
  };
}

const state = setup();
assert.deepStrictEqual(state.visible(), ["A", "B", "C", "D", "E", "F", "G"]);
for (const [band, expected] of [
  ["under-1000", ["A", "G"]], ["1000-1999", ["B", "C"]],
  ["2000-2999", ["D", "E"]], ["3000-plus", ["F"]],
]) {
  // These are displayed lower-bound bands, NOT guaranteed purchase budgets.
  state.change("price", band);
  assert.deepStrictEqual(state.visible(), expected);
  assert.strictEqual(state.resultCount.textContent, `${expected.length}\u4ef6`);
  assert.strictEqual(state.pageStatus.textContent, `7\u4ef6\u4e2d${expected.length}\u4ef6\u3092\u8868\u793a`);
}
state.change("price", "all");
state.change("search", "  \uff21\uff2c\uff30\uff28\uff21  ");
assert.deepStrictEqual(state.visible(), ["A", "G"]);
state.change("price", "3000-plus");
assert.deepStrictEqual(state.visible(), []);
assert.strictEqual(state.resultCount.textContent, "0\u4ef6");
state.change("search", "");
state.change("price", "all");
for (const [sort, expected] of [
  ["price-asc", ["A", "G", "B", "C", "D", "E", "F"]],
  ["price-desc", ["F", "E", "D", "C", "B", "A", "G"]],
  ["observed-desc", ["A", "G", "B", "C", "D", "E", "F"]],
  ["observed-asc", ["F", "E", "D", "C", "B", "A", "G"]],
  ["original", ["A", "B", "C", "D", "E", "F", "G"]],
]) { state.change("sort", sort); assert.deepStrictEqual(state.visible(), expected); }
assert.deepStrictEqual(setup({ params: "?price_band=1000-1999&sort=price-desc" }).visible(), ["C", "B"]);
for (const mode of ["absent", "denied", "throws", "granted"]) {
  const s = setup({ mode });
  assert.doesNotThrow(() => assert.strictEqual(s.click(), false));
  assert.strictEqual(s.events.length, mode === "granted" ? 2 : 0);
  if (mode === "granted") {
    assert.strictEqual(s.events[0].name, "view_item_list");
    assert.strictEqual(s.events[0].context, undefined);
    const outbound = s.events[1];
    assert.strictEqual(outbound.name, "outbound_product_click");
    assert.deepStrictEqual(Object.keys(outbound.context).sort(), ["public_id", "surface"]);
    assert.strictEqual(outbound.context.public_id, "itm_0123456789abcdef01234567");
    assert.strictEqual(outbound.context.surface, "product_card");
  }
  s.listeners.dataLabAnalyticsReady();
  s.listeners.DOMContentLoaded();
  assert.strictEqual(s.events.length, mode === "granted" ? 2 : 0);
}
for (const href of ["https://example.invalid/", "/go/not-an-id", "/go/itm_0123456789abcdef01234567?x=1"]) {
  const s = setup({ mode: "granted", href });
  assert.strictEqual(s.click(), false);
  assert.strictEqual(s.events.length, 1);
}
