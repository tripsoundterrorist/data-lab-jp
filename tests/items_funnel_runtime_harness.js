"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..");
const source = fs.readFileSync(path.join(ROOT, "items", "items.js"), "utf8");
const ITEM_ID = "itm_0123456789abcdef01234567";
const OBSERVED_AT = "2026-09-05T07:00:21Z";

class FakeElement {
  constructor(tagName = "div") {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.listeners = new Map();
    this.attributes = new Map();
    this.className = "";
    this.dataset = {};
    this.style = {};
    this.hidden = false;
    this.disabled = false;
    this.value = "";
    this.textContent = "";
  }

  get firstChild() {
    return this.children[0] || null;
  }

  append(...children) {
    this.children.push(...children);
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  removeChild(child) {
    const index = this.children.indexOf(child);
    if (index >= 0) this.children.splice(index, 1);
    return child;
  }

  addEventListener(name, callback) {
    const callbacks = this.listeners.get(name) || [];
    callbacks.push(callback);
    this.listeners.set(name, callbacks);
  }

  trigger(name) {
    for (const callback of this.listeners.get(name) || []) callback({ currentTarget: this });
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  focus() {}

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }

  querySelectorAll(selector) {
    const className = selector.startsWith(".") ? selector.slice(1) : null;
    const matches = [];
    const visit = (node) => {
      if (className && node.className.split(/\s+/u).includes(className)) matches.push(node);
      for (const child of node.children || []) visit(child);
    };
    for (const child of this.children) visit(child);
    return matches;
  }
}

function label() {
  return { code: "high", en: "High", ja: "高い" };
}

function priceSummary() {
  return {
    version: "0.1",
    observed_set_percentile: 50,
    percentile_method: "nearest_rank",
    price_band: { code: "middle", en: "Middle", ja: "中価格帯" },
  };
}

function indexItem(valid = true) {
  return {
    public_id: ITEM_ID,
    title: valid ? "Runtime fixture" : "",
    image_url: null,
    current_price: 1980,
    data_confidence: { score: 85.6, label: label(), version: "0.1" },
    price_analysis: priceSummary(),
    last_observed_at: OBSERVED_AT,
  };
}

function detailItem() {
  return {
    public_id: ITEM_ID,
    title: "Runtime fixture",
    image_url: null,
    item_url: "https://www.dmm.co.jp/digital/videoa/-/detail/=/cid=runtimefixture/",
    affiliate_cta_eligible: false,
    metadata: { maker: [], series: [], actress: [], genre: [] },
    current_price: 1980,
    price_observed_at: OBSERVED_AT,
    last_observed_at: OBSERVED_AT,
    data_confidence: {
      score: 85.6,
      label: label(),
      version: "0.1",
      components: {
        freshness: 100,
        observation_depth: 80,
        metadata_completeness: 75,
        price_data: 90,
        temporal_confidence: 50,
      },
      warnings: [],
    },
    price_analysis: {
      ...priceSummary(),
      genre_comparisons: [],
      maker_comparison: { available: false, comparisons: [] },
      price_history: {
        price_observation_count: 5,
        distinct_price_observation_dates: 5,
        price_observation_span_days: 4,
        min_observed_price: 1980,
        max_observed_price: 1980,
      },
      warnings: [],
    },
  };
}

function manifest() {
  return {
    public_schema_version: "0.1",
    publication_status: "local_validation_only",
    rights_review_required: ["title"],
    item_count: 1,
    as_of: OBSERVED_AT,
  };
}

function documentFixture(page) {
  const elements = new Map();
  const ids = [
    "data-fallback", "data-content", "detail-root", "publication-status",
    "item-grid", "result-count", "page-status", "prev-page", "next-page",
    "search", "sort", "confidence-filter", "band-filter", "item-count", "as-of",
  ];
  for (const id of ids) elements.set(id, new FakeElement());
  elements.get("sort").value = "observed-desc";
  elements.get("data-content").hidden = true;
  elements.get("detail-root").hidden = true;
  elements.get("data-fallback").hidden = true;

  const body = new FakeElement("body");
  body.dataset.page = page;
  const footer = new FakeElement("footer");
  return {
    body,
    createElement: (tag) => new FakeElement(tag),
    getElementById: (id) => elements.get(id) || null,
    querySelector: (selector) => selector === "footer" ? footer : null,
    addEventListener: (name, callback) => {
      if (name === "DOMContentLoaded") callback();
    },
    elements,
  };
}

async function runScenario(page, valid = true) {
  const events = [];
  const document = documentFixture(page);
  const location = {
    hostname: "127.0.0.1",
    search: page === "detail" ? `?id=${ITEM_ID}` : "",
  };
  const responses = new Map([
    ["/data/manifest.json", manifest()],
    ["/data/index.json", {
      public_schema_version: "0.1",
      generated_at: OBSERVED_AT,
      as_of: OBSERVED_AT,
      items: [indexItem(valid)],
    }],
    [`/data/items/01/${ITEM_ID}.json`, {
      public_schema_version: "0.1",
      generated_at: OBSERVED_AT,
      as_of: OBSERVED_AT,
      item: detailItem(),
    }],
  ]);
  const window = {
    location,
    dataLabAnalytics: {
      trackEvent(name) {
        events.push(name);
        return true;
      },
    },
  };
  const fetch = async (url) => ({
    ok: responses.has(url),
    async json() {
      return responses.get(url);
    },
  });

  vm.runInNewContext(source, {
    window,
    document,
    fetch,
    URL,
    URLSearchParams,
    Intl,
    Date,
    Set,
    Map,
    Object,
    Number,
    console,
  }, { filename: "items/items.js" });
  await new Promise((resolve) => setTimeout(resolve, 20));
  return { document, events };
}

(async () => {
  const index = await runScenario("index");
  assert.deepStrictEqual(index.events, ["view_item_list"]);
  const detailLinks = index.document.elements.get("item-grid").querySelectorAll(".detail-link");
  assert.strictEqual(detailLinks.length, 1);
  detailLinks[0].trigger("click");
  assert.deepStrictEqual(index.events, ["view_item_list", "select_item"]);

  const detail = await runScenario("detail");
  assert.deepStrictEqual(detail.events, ["view_item"]);
  const officialLinks = detail.document.elements.get("detail-root").querySelectorAll(".official-link");
  assert.strictEqual(officialLinks.length, 1);
  officialLinks[0].trigger("click");
  assert.deepStrictEqual(detail.events, ["view_item", "outbound_product_click"]);

  const invalid = await runScenario("index", false);
  assert.deepStrictEqual(invalid.events, []);
  assert.strictEqual(invalid.document.elements.get("data-fallback").hidden, false);
  assert.strictEqual(invalid.document.elements.get("data-content").hidden, true);
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
