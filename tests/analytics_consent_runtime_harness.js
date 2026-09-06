"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const script = fs.readFileSync(
  path.resolve(__dirname, "..", "analytics-consent.js"),
  "utf8"
);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function scenario(initialChoice) {
  const storage = new Map();
  if (initialChoice !== null) {
    storage.set("datalabx.analytics-consent.v1", initialChoice);
  }
  const bodyChildren = [];
  const headChildren = [];
  const domListeners = new Map();
  let reloadCount = 0;

  class Element {
    constructor(tag) {
      this.tagName = tag.toUpperCase();
      this.className = "";
      this.hidden = false;
      this.dataset = {};
      this.listeners = new Map();
      this.children = [];
      this._controls = new Map();
    }
    setAttribute() {}
    appendChild(child) { this.children.push(child); return child; }
    append(...children) { this.children.push(...children); }
    addEventListener(name, callback) { this.listeners.set(name, callback); }
    focus() {}
    querySelector(selector) {
      if (!this._controls.has(selector)) {
        this._controls.set(selector, new Element("button"));
      }
      if (selector === "button") {
        return this.querySelector(".analytics-consent__accept");
      }
      return this._controls.get(selector);
    }
    trigger(name) {
      const callback = this.listeners.get(name);
      if (callback) callback();
    }
  }

  const footer = new Element("footer");
  const document = {
    body: {
      appendChild(element) { bodyChildren.push(element); return element; }
    },
    head: {
      appendChild(element) { headChildren.push(element); return element; }
    },
    createElement(tag) { return new Element(tag); },
    querySelector(selector) {
      return selector === "footer .container" || selector === "footer"
        ? footer : null;
    },
    addEventListener(name, callback) { domListeners.set(name, callback); }
  };
  const window = {
    location: {
      origin: "https://datalabx.jp",
      pathname: "/items/item",
      search: "?id=secret",
      hash: "#secret",
      reload() { reloadCount += 1; }
    },
    localStorage: {
      getItem(key) { return storage.has(key) ? storage.get(key) : null; },
      setItem(key, value) { storage.set(key, value); }
    }
  };

  vm.runInNewContext(script, { window, document, console });
  domListeners.get("DOMContentLoaded")();

  return {
    window,
    storage,
    bodyChildren,
    headChildren,
    get reloadCount() { return reloadCount; }
  };
}

const noChoice = scenario(null);
assert(noChoice.headChildren.length === 0, "script loaded before choice");
assert(typeof noChoice.window.gtag === "undefined", "gtag created before choice");
assert(typeof noChoice.window.dataLayer === "undefined", "dataLayer created before choice");
assert(noChoice.bodyChildren[0].hidden === false, "banner hidden without choice");
assert(
  noChoice.window.dataLabAnalytics.trackEvent("view_item") === false,
  "event accepted before consent"
);

const denied = scenario("denied");
assert(denied.headChildren.length === 0, "script loaded after denial");
assert(typeof denied.window.gtag === "undefined", "gtag created after denial");
assert(
  denied.window.dataLabAnalytics.trackEvent("view_item") === false,
  "event accepted after denial"
);

const accepted = scenario(null);
const panel = accepted.bodyChildren[0];
panel.querySelector(".analytics-consent__accept").trigger("click");
assert(
  accepted.storage.get("datalabx.analytics-consent.v1") === "granted",
  "grant not persisted"
);
assert(accepted.headChildren.length === 1, "Google script not loaded after grant");
assert(
  accepted.headChildren[0].src ===
    "https://www.googletagmanager.com/gtag/js?id=G-ZPBQJ6137L",
  "unexpected Google script source"
);
assert(
  accepted.window.dataLabAnalytics.trackEvent("view_item") === true,
  "allowlisted event rejected after grant"
);
assert(
  accepted.window.dataLabAnalytics.trackEvent("secret_event") === false,
  "non-allowlisted event accepted"
);

const commands = accepted.window.dataLayer.map((entry) => Array.from(entry));
assert(commands[0][0] === "consent" && commands[0][1] === "default", "default consent missing");
assert(commands[0][2].analytics_storage === "denied", "analytics default not denied");
assert(commands[0][2].ad_storage === "denied", "ad storage default not denied");
assert(commands[1][0] === "consent" && commands[1][1] === "update", "grant update missing");
assert(commands[1][2].analytics_storage === "granted", "analytics grant missing");
const pageView = commands.find((entry) => entry[0] === "event" && entry[1] === "page_view");
assert(pageView[2].page_location === "https://datalabx.jp/items/item", "query leaked");
assert(pageView[2].page_referrer === "", "referrer leaked");
const viewItem = commands.find((entry) => entry[0] === "event" && entry[1] === "view_item");
assert(viewItem.length === 2, "funnel event contains parameters");

const revoked = scenario("granted");
const revokedPanel = revoked.bodyChildren[0];
revokedPanel.querySelector(".analytics-consent__deny").trigger("click");
assert(
  revoked.storage.get("datalabx.analytics-consent.v1") === "denied",
  "denial not persisted"
);
assert(revoked.reloadCount === 1, "loaded analytics not cleared by reload");
