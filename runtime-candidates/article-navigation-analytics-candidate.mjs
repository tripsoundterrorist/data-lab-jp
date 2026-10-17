// Offline candidate only. No browser globals, network, storage or auto-install.
// A future consent-owned adapter requires separate integration/send approval.
const ROUTES = Object.freeze([
  Object.freeze({from: "/coupon-help", to: "/column-price", label: "coupon_to_price"}),
  Object.freeze({from: "/books-device-check", to: "/column-price", label: "device_to_price"}),
  Object.freeze({from: "/column-price", to: "/items/", label: "price_to_items"}),
]);

export function createArticleNavigationObserver(readConsent, record) {
  // Injected record is an offline mock here, not an authorization to send.
  return function observeNavigation(input) {
    try {
      if (typeof readConsent !== "function" || typeof record !== "function") return false;
      if (!input || typeof input !== "object" || Array.isArray(input)) return false;
      const keys = Reflect.ownKeys(input);
      if (keys.length !== 2 || !keys.includes("from") || !keys.includes("to")) return false;
      const route = ROUTES.find(entry => entry.from === input.from && entry.to === input.to);
      if (!route || readConsent() !== "granted") return false;
      return record(Object.freeze({
        event_name: "article_navigation_click",
        navigation_route: route.label,
      })) === true;
    } catch (_) {
      // No throw, buffering, retry, preventDefault, or navigation modification.
      return false;
    }
  };
}
