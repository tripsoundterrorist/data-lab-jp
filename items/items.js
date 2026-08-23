"use strict";

const DATA_ROOT = "/data";
const EXPECTED_SCHEMA_VERSION = "0.1";
const EXPECTED_PUBLICATION_STATUS = "public";
const PAGE_SIZE = 24;
const state = { items: [], filtered: [], page: 1 };

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function formatPrice(value) {
  if (!Number.isFinite(value)) return "価格データなし";
  return new Intl.NumberFormat("ja-JP", { style: "currency", currency: "JPY", maximumFractionDigits: 0 }).format(value);
}

function formatDate(value) {
  const date = value ? new Date(value) : null;
  if (!date || Number.isNaN(date.getTime())) return "観測時刻なし";
  return new Intl.DateTimeFormat("ja-JP", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

async function fetchJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error("PUBLIC_DATA_UNAVAILABLE");
  return response.json();
}

function validateManifest(manifest) {
  const valid = manifest
    && manifest.public_schema_version === EXPECTED_SCHEMA_VERSION
    && manifest.publication_status === EXPECTED_PUBLICATION_STATUS
    && Array.isArray(manifest.rights_review_required)
    && manifest.rights_review_required.length === 0;
  if (!valid) throw new Error("PUBLIC_DATA_NOT_PUBLISHABLE");
}

function showData() {
  document.getElementById("data-fallback").hidden = true;
  const content = document.getElementById("data-content") || document.getElementById("detail-root");
  content.hidden = false;
  document.getElementById("publication-status").textContent = "公開データ";
}

function showFallback() {
  const fallback = document.getElementById("data-fallback");
  if (fallback) fallback.hidden = false;
  const content = document.getElementById("data-content") || document.getElementById("detail-root");
  if (content) content.hidden = true;
  const status = document.getElementById("publication-status");
  if (status) status.textContent = "公開準備中";
}

function metric(label, value) {
  const box = element("div", "metric");
  box.append(element("span", "metric-label", label), element("span", "metric-value", value));
  return box;
}

function imageBlock(item, detail) {
  const wrap = element("div", detail ? "card-image-wrap detail-image-wrap" : "card-image-wrap");
  const placeholder = element("span", "image-placeholder", "画像データなし");
  if (!item.image_url) { wrap.append(placeholder); return wrap; }
  const image = element("img", "card-image");
  image.src = item.image_url;
  image.alt = item.title || "商品画像";
  image.loading = "lazy";
  image.decoding = "async";
  image.hidden = true;
  image.addEventListener("load", () => { clear(wrap); image.hidden = false; wrap.append(image); });
  image.addEventListener("error", () => { clear(wrap); wrap.append(placeholder); });
  wrap.append(placeholder, image);
  return wrap;
}

function card(item) {
  const article = element("article", "item-card");
  article.append(imageBlock(item, false));
  const body = element("div", "card-body");
  body.append(element("h2", "card-title", item.title), element("p", "price", formatPrice(item.current_price)));
  const metrics = element("div", "metrics");
  metrics.append(metric("データ信頼度", `${item.data_confidence.score.toFixed(1)} / 100 · ${item.data_confidence.label.ja}`));
  const percentile = item.price_analysis.observed_set_percentile;
  metrics.append(metric("価格位置", percentile === null ? "データなし" : `観測セット内 約${Math.round(percentile)}%`));
  body.append(metrics, element("p", "observed-at", `最終観測 ${formatDate(item.last_observed_at)}`));
  const link = element("a", "detail-link", "詳細を見る");
  link.href = `item.html?id=${encodeURIComponent(item.public_id)}`;
  body.append(link);
  article.append(body);
  return article;
}

function renderPage() {
  const grid = document.getElementById("item-grid");
  clear(grid);
  const pages = Math.max(1, Math.ceil(state.filtered.length / PAGE_SIZE));
  state.page = Math.min(state.page, pages);
  const start = (state.page - 1) * PAGE_SIZE;
  state.filtered.slice(start, start + PAGE_SIZE).forEach((item) => grid.append(card(item)));
  if (!state.filtered.length) grid.append(element("p", "muted", "条件に一致するデータがありません。"));
  document.getElementById("result-count").textContent = `${state.filtered.length}件を表示対象にしています`;
  document.getElementById("page-status").textContent = `${state.page} / ${pages}`;
  document.getElementById("prev-page").disabled = state.page <= 1;
  document.getElementById("next-page").disabled = state.page >= pages;
}

function applyFilters() {
  const query = document.getElementById("search").value.trim().toLocaleLowerCase("ja-JP");
  const confidence = document.getElementById("confidence-filter").value;
  const band = document.getElementById("band-filter").value;
  const sort = document.getElementById("sort").value;
  state.filtered = state.items.filter((item) => {
    const itemBand = item.price_analysis.price_band?.code || "";
    return (!query || item.title.toLocaleLowerCase("ja-JP").includes(query))
      && (!confidence || item.data_confidence.label.code === confidence)
      && (!band || itemBand === band);
  });
  const finite = (value, fallback) => Number.isFinite(value) ? value : fallback;
  state.filtered.sort((a, b) => {
    if (sort === "price-asc") return finite(a.current_price, Infinity) - finite(b.current_price, Infinity);
    if (sort === "price-desc") return finite(b.current_price, -Infinity) - finite(a.current_price, -Infinity);
    if (sort === "confidence-desc") return b.data_confidence.score - a.data_confidence.score;
    return new Date(b.last_observed_at).getTime() - new Date(a.last_observed_at).getTime();
  });
  state.page = 1;
  renderPage();
}

function populateFilter(id, entries) {
  const select = document.getElementById(id);
  [...entries].sort((a, b) => a[0].localeCompare(b[0])).forEach(([value, label]) => {
    const option = element("option", "", label);
    option.value = value;
    select.append(option);
  });
}

async function initializeIndex() {
  const [manifest, index] = await Promise.all([
    fetchJson(`${DATA_ROOT}/manifest.json`),
    fetchJson(`${DATA_ROOT}/index.json`),
  ]);
  validateManifest(manifest);
  if (!index || !Array.isArray(index.items) || index.items.length !== manifest.item_count) throw new Error("PUBLIC_DATA_INVALID");
  state.items = index.items.slice();
  document.getElementById("item-count").textContent = `${manifest.item_count} items`;
  document.getElementById("as-of").textContent = formatDate(manifest.as_of);
  populateFilter("confidence-filter", new Map(state.items.map((item) => [item.data_confidence.label.code, item.data_confidence.label.ja])));
  populateFilter("band-filter", new Map(state.items.filter((item) => item.price_analysis.price_band).map((item) => [item.price_analysis.price_band.code, item.price_analysis.price_band.ja])));
  ["search", "sort", "confidence-filter", "band-filter"].forEach((id) => document.getElementById(id).addEventListener(id === "search" ? "input" : "change", applyFilters));
  document.getElementById("prev-page").addEventListener("click", () => { state.page -= 1; renderPage(); });
  document.getElementById("next-page").addEventListener("click", () => { state.page += 1; renderPage(); });
  showData();
  applyFilters();
}

function definitionList(entries) {
  const list = element("dl", "stats-list");
  entries.forEach(([label, value]) => list.append(element("dt", "", label), element("dd", "", value)));
  return list;
}

function detailPanel(title, content) {
  const panel = element("section", "panel detail-panel");
  panel.append(element("h2", "", title), content);
  return panel;
}

function confidencePanel(data) {
  const panel = element("section", "panel detail-panel");
  panel.append(element("h2", "", "データ信頼度の内訳"));
  panel.append(element("p", "", `総合：${data.score.toFixed(1)} / 100 · ${data.label.ja}`));
  panel.append(element("p", "muted", "この指標は作品の品質・人気・内容を評価するものではありません。"));
  const labels = new Map([
    ["freshness", "鮮度"], ["observation_depth", "観測深度"],
    ["metadata_completeness", "基本情報"], ["price_data", "価格データ"],
    ["temporal_confidence", "時系列信頼度"],
  ]);
  Object.entries(data.components).forEach(([key, value]) => {
    const row = element("div", "component");
    const head = element("div", "component-head");
    head.append(element("span", "", labels.get(key) || key), element("span", "", `${Number(value).toFixed(1)} / 100`));
    const bar = element("div", "bar");
    const fill = element("div", "bar-fill");
    fill.style.width = `${Math.max(0, Math.min(100, Number(value)))}%`;
    bar.append(fill);
    row.append(head, bar);
    panel.append(row);
  });
  return panel;
}

function pricePanel(item) {
  const analysis = item.price_analysis;
  const history = analysis.price_history;
  return detailPanel("価格分析", definitionList([
    ["現在価格", formatPrice(item.current_price)],
    ["観測セット内の価格位置", analysis.observed_set_percentile === null ? "データなし" : `約${Math.round(analysis.observed_set_percentile)}%`],
    ["価格位置帯", analysis.price_band ? analysis.price_band.ja : "データなし"],
    ["価格観測回数", `${history.price_observation_count}回`],
    ["異なる観測日", `${history.distinct_price_observation_dates}日`],
    ["価格観測期間", `${Number(history.price_observation_span_days).toFixed(2)}日`],
    ["最小観測価格", formatPrice(history.min_observed_price)],
    ["最大観測価格", formatPrice(history.max_observed_price)],
  ]));
}

function metadataPanel(metadata) {
  const panel = element("section", "panel detail-panel");
  panel.append(element("h2", "", "基本情報"));
  const labels = new Map([["maker", "メーカー"], ["series", "シリーズ"], ["actress", "出演者"], ["genre", "ジャンル"]]);
  Object.entries(metadata).forEach(([key, entities]) => {
    if (!Array.isArray(entities) || !entities.length) return;
    const group = element("div", "metadata-group");
    group.append(element("h3", "", labels.get(key) || key));
    const tags = element("div", "tag-list");
    entities.forEach((entity) => tags.append(element("span", "tag", entity.name)));
    group.append(tags);
    panel.append(group);
  });
  return panel;
}

function comparisonPanel(title, entityLabel, comparisons, entities, minimum) {
  const panel = element("section", "panel detail-panel");
  panel.append(element("h2", "", title));
  const names = new Map(entities.map((entity) => [entity.public_id, entity.name]));
  const available = comparisons.filter((entry) => entry.status === "available" && entry.sample_size >= minimum);
  if (!available.length) { panel.append(element("p", "muted", "比較データ不足")); return panel; }
  available.forEach((entry, index) => {
    const row = element("div", "comparison");
    if (index >= 4) row.hidden = true;
    row.append(element("p", "", `${entityLabel}：${names.get(entry.public_group_id) || "表示データなし"}`));
    row.append(element("p", "muted", `標本数 ${entry.sample_size} · 観測セット内位置 約${Math.round(entry.percentile)}%`));
    row.append(element("p", "muted", `中央値 ${formatPrice(entry.median)}`));
    panel.append(row);
  });
  if (available.length > 4) {
    const toggle = element("button", "comparison-toggle", `すべて表示（${available.length}件）`);
    toggle.type = "button";
    toggle.addEventListener("click", () => {
      const expand = toggle.dataset.expanded !== "true";
      panel.querySelectorAll(".comparison").forEach((row, index) => { row.hidden = !expand && index >= 4; });
      toggle.dataset.expanded = String(expand);
      toggle.textContent = expand ? "表示を戻す" : `すべて表示（${available.length}件）`;
    });
    panel.append(toggle);
  }
  return panel;
}

function renderDetail(item) {
  const root = document.getElementById("detail-root");
  clear(root);
  const hero = element("section", "panel detail-hero");
  hero.append(imageBlock(item, true));
  const copy = element("div", "detail-copy");
  copy.append(element("p", "section-label", "OBSERVATION DETAIL"), element("h2", "detail-title", item.title), element("p", "price", formatPrice(item.current_price)), element("p", "muted", `最終観測 ${formatDate(item.last_observed_at)}`));
  if (item.item_url) {
    const official = element("a", "official-link", "公式ページを見る");
    official.href = item.item_url;
    official.target = "_blank";
    official.rel = "noopener noreferrer";
    copy.append(official);
  }
  hero.append(copy);
  root.append(hero);
  const grid = element("div", "detail-grid");
  grid.append(confidencePanel(item.data_confidence));
  grid.append(pricePanel(item));
  grid.append(metadataPanel(item.metadata));
  grid.append(comparisonPanel("ジャンル内価格比較", "ジャンル", item.price_analysis.genre_comparisons, item.metadata.genre, 20));
  grid.append(comparisonPanel("メーカー内価格比較", "メーカー", item.price_analysis.maker_comparison.comparisons, item.metadata.maker, 10));
  root.append(grid);
}

async function initializeDetail() {
  const id = new URLSearchParams(window.location.search).get("id");
  if (!id || !/^itm_[0-9a-f]{24}$/.test(id)) throw new Error("PUBLIC_ID_INVALID");
  const manifest = await fetchJson(`${DATA_ROOT}/manifest.json`);
  validateManifest(manifest);
  const detail = await fetchJson(`${DATA_ROOT}/items/${id.slice(4, 6)}/${encodeURIComponent(id)}.json`);
  if (!detail || detail.public_schema_version !== EXPECTED_SCHEMA_VERSION || detail.item?.public_id !== id) throw new Error("PUBLIC_DATA_INVALID");
  renderDetail(detail.item);
  showData();
}

document.addEventListener("DOMContentLoaded", () => {
  const initialize = document.body.dataset.page === "detail" ? initializeDetail : initializeIndex;
  initialize().catch(() => showFallback());
});
