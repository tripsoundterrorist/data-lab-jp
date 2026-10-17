// Local opt-in output only. Ordinary public build never includes this module.
import { installArticleNavigationAdapter } from "./article-navigation-dom-adapter-candidate.mjs";
import { createArticleNavigationRecorder } from "./article-navigation-ga4-bridge-candidate.mjs";

export function installNavigationBootstrap(page, root) {
  try {
    if (!["/coupon-help", "/books-device-check", "/column-price"].includes(page.location.pathname)) return null;
    const readConsent = () => page.dataLabAnalytics?.readConsent?.() ?? null;
    const invoke = (...args) => {
      if (typeof page.gtag !== "function") throw Error("ANALYTICS_UNAVAILABLE");
      page.gtag(...args);
    };
    return installArticleNavigationAdapter(
      root, () => page.location.pathname, readConsent,
      createArticleNavigationRecorder(readConsent, invoke),
    );
  } catch (_) {
    return null;
  }
}

if (typeof window !== "undefined" && typeof document !== "undefined") {
  installNavigationBootstrap(window, document);
}
