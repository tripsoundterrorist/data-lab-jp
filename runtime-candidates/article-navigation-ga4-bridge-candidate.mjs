// Offline-only bridge. Does not acquire a browser, configure GA4 or install itself.
// Both functions are synchronous injected capabilities; tests supply mocks only.
const SOURCES = Object.freeze({
  coupon_to_price: "/coupon-help",
  device_to_price: "/books-device-check",
  price_to_items: "/column-price",
});

export function createArticleNavigationRecorder(readConsent, invokeEvent) {
  return function recordNavigation(input) {
    try {
      if (typeof readConsent !== "function" || typeof invokeEvent !== "function") return false;
      if (!input || typeof input !== "object" || Array.isArray(input)) return false;
      const keys = Reflect.ownKeys(input);
      if (keys.length !== 2 || !keys.includes("event_name") || !keys.includes("navigation_route")) return false;
      const name = input.event_name;
      const label = input.navigation_route;
      if (name !== "article_navigation_click" || typeof label !== "string" ||
          !Object.hasOwn(SOURCES, label)) return false;
      const pathname = SOURCES[label];
      if (readConsent() !== "granted") return false;
      invokeEvent("event", name, Object.freeze({
        navigation_route: label,
        page_location: "https://datalabx.jp" + pathname,
        page_path: pathname,
        page_referrer: "",
      }));
      // Invocation only, not proof of network delivery, processing or attribution.
      return true;
    } catch (_) {
      return false;
    }
  };
}
