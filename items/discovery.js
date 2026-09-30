(() => {
  "use strict";

  const grid = document.querySelector(".item-grid");
  const search = document.querySelector("#item-search");
  const priceFilter = document.querySelector("#price-filter");
  const sort = document.querySelector("#item-sort");
  const resultCount = document.querySelector("#result-count");
  const pageStatus = document.querySelector("#page-status");
  if (!grid || !search || !priceFilter || !sort || !resultCount || !pageStatus) return;

  const trackFunnelEvent = (name) => {
    try {
      return window.dataLabAnalytics?.trackEvent(name) === true;
    } catch (_) {
      return false;
    }
  };
  let listViewTracked = false;
  const trackListView = () => {
    if (listViewTracked) return;
    listViewTracked = trackFunnelEvent("view_item_list");
  };

  const normalize = (value) => value.normalize("NFKC").toLocaleLowerCase("ja").trim();
  const allowedPriceBands = new Set(["all", "under-1000", "1000-1999", "2000-2999", "3000-plus"]);
  const allowedSorts = new Set(["original", "price-asc", "price-desc", "observed-desc", "observed-asc"]);
  const incoming = new URLSearchParams(window.location?.search || "");
  const incomingPriceBand = incoming.get("price_band");
  const incomingSort = incoming.get("sort");
  if (allowedPriceBands.has(incomingPriceBand)) priceFilter.value = incomingPriceBand;
  if (allowedSorts.has(incomingSort)) sort.value = incomingSort;
  const cards = Array.from(grid.querySelectorAll(":scope > .item")).map((element, index) => {
    const priceText = element.querySelector(".price")?.textContent || "";
    const observedText = element.querySelector("time")?.textContent || "";
    const priceDigits = priceText.replace(/[^0-9]/g, "");
    const observedValue = Date.parse(observedText);
    return {
      element,
      index,
      title: normalize(element.querySelector("h2")?.textContent || ""),
      price: priceDigits ? Number(priceDigits) : Number.NaN,
      observed: Number.isFinite(observedValue) ? observedValue : Number.NEGATIVE_INFINITY,
    };
  });

  const inPriceBand = (price, band) => {
    if (!Number.isFinite(price)) return false;
    if (band === "under-1000") return price < 1000;
    if (band === "1000-1999") return price >= 1000 && price < 2000;
    if (band === "2000-2999") return price >= 2000 && price < 3000;
    if (band === "3000-plus") return price >= 3000;
    return true;
  };

  const compare = (left, right) => {
    if (sort.value === "price-asc") return left.price - right.price || left.index - right.index;
    if (sort.value === "price-desc") return right.price - left.price || left.index - right.index;
    if (sort.value === "observed-desc") return right.observed - left.observed || left.index - right.index;
    if (sort.value === "observed-asc") return left.observed - right.observed || left.index - right.index;
    return left.index - right.index;
  };

  const update = () => {
    const query = normalize(search.value);
    const visible = cards.filter((card) => card.title.includes(query) && inPriceBand(card.price, priceFilter.value));
    const visibleSet = new Set(visible);
    cards.forEach((card) => { card.element.hidden = !visibleSet.has(card); });
    visible.sort(compare).forEach((card) => grid.append(card.element));
    resultCount.textContent = `${visible.length}件`;
    pageStatus.textContent = visible.length === cards.length ? "全商品を表示" : `${cards.length}件中${visible.length}件を表示`;
  };

  search.addEventListener("input", update);
  priceFilter.addEventListener("change", update);
  sort.addEventListener("change", update);
  document.querySelectorAll(".affiliate-cta-link").forEach((link) => {
    link.addEventListener("click", () => trackFunnelEvent("outbound_product_click"));
  });
  document.querySelectorAll(".card-image").forEach((image) => {
    image.addEventListener("error", () => {
      const wrapper = image.closest(".card-image-wrap");
      if (!wrapper) return;
      const placeholder = document.createElement("span");
      placeholder.className = "image-placeholder";
      placeholder.textContent = "画像を取得できませんでした";
      image.remove();
      wrapper.append(placeholder);
    }, { once: true });
  });
  document.addEventListener("dataLabAnalyticsReady", trackListView);
  document.addEventListener("DOMContentLoaded", trackListView);
  update();
})();
