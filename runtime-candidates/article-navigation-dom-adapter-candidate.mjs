// Explicitly installed offline candidate; not part of the public build.
// All capabilities are injected. readConsent and record must be synchronous.
import { createArticleNavigationObserver } from "./article-navigation-analytics-candidate.mjs";

const installations = new WeakMap();

export function installArticleNavigationAdapter(root, getPathname, readConsent, record) {
  try {
    if (!root || typeof root.addEventListener !== "function" ||
        typeof root.removeEventListener !== "function" || typeof root.contains !== "function" ||
        typeof getPathname !== "function" || typeof readConsent !== "function" ||
        typeof record !== "function") return null;
    if (installations.has(root)) return installations.get(root);
    const observe = createArticleNavigationObserver(readConsent, record);
    let active = true;
    function onClick(event) {
      try {
        if (!active || !event || event.defaultPrevented || event.button !== 0 ||
            event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        const element = event.target?.nodeType === 3 ? event.target.parentElement : event.target;
        const anchor = element?.closest?.("a[href]");
        if (!anchor || !root.contains(anchor) || !anchor.closest("article") ||
            anchor.hasAttribute("download")) return;
        const target = anchor.getAttribute("target");
        if (target !== null && target !== "" && target !== "_self") return;
        // Raw href and exact pathname only: no URL parsing, queries or referrers.
        observe({from: getPathname(), to: anchor.getAttribute("href")});
      } catch (_) {
        // Never interfere with native navigation or retry failed observations.
      }
    }
    function uninstall() {
      if (!active) return;
      active = false;
      try { root.removeEventListener("click", onClick, false); } catch (_) {}
      installations.delete(root);
    }
    root.addEventListener("click", onClick, false);
    installations.set(root, uninstall);
    return uninstall;
  } catch (_) {
    return null;
  }
}
