"use strict";

const EXPECTED_SCHEMA_VERSION = "0.1";
const EXPECTED_POLICY_VERSION = "0.1";
const EXPECTED_PUBLICATION_STATUS = "local_validation_only";
const PAGE_SIZE = 24;

const state = {
  items: [],
  filtered: [],
  page: 1,
};

function createElement(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function clearNode(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function formatPrice(value) {
  if (!Number.isFinite(value)) return "価格データなし";
  return new Intl.NumberFormat("ja-JP", { style: "currency", currency: "JPY", maximumFractionDigits: 0 }).format(value);
}

function formatDate(value) {
  if (!value) return "観測時刻なし";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "観測時刻不明";
  return new Intl.DateTimeFormat("ja-JP", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function validateManifest(manifest) {
  const valid = manifest
    && manifest.public_schema_version === EXPECTED_SCHEMA_VERSION
    && manifest.public_policy_version === EXPECTED_POLICY_VERSION
    && manifest.publication_status === EXPECTED_PUBLICATION_STATUS
    && Array.isArray(manifest.rights_review_required);
  if (!valid) throw new Error("データ形式が一致しません");
}

async function fetchJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`データを取得できません (${response.status})`);
  return response.json();
}

function setPreviewStatus(manifest) {
  const status = document.getElementById("preview-status");
  if (!status) return;
  const pending = manifest.rights_review_required.length > 0;
  status.textContent = pending ? "LOCAL PREVIEW · Rights review pending" : "LOCAL PREVIEW";
}

function metric(label, value) {
  const box = createElement("div", "metric");
  box.append(createElement("span", "metric-label", label));
  box.append(createElement("span", "metric-value", value));
  return box;
}

function imageBlock(item, detail) {
  const wrap = createElement("div", detail ? "card-image-wrap detail-image-wrap" : "card-image-wrap");
  const placeholder = createElement("span", "image-placeholder", "IMAGE NOT AVAILABLE");
  if (!item.image_url) {
    placeholder.textContent = "画像データなし";
    wrap.append(placeholder);
    return wrap;
  }
  const image = createElement("img", "card-image");
  image.src = item.image_url;
  image.alt = item.title || "商品画像";
  image.loading = "lazy";
  image.decoding = "async";
  image.hidden = true;
  image.addEventListener("load", () => {
    clearNode(wrap);
    image.hidden = false;
    wrap.append(image);
  });
  image.addEventListener("error", () => {
    clearNode(wrap);
    placeholder.textContent = "画像データなし";
    wrap.append(placeholder);
  });
  wrap.append(placeholder, image);
  return wrap;
}

function makeCard(item) {
  const card = createElement("article", "item-card");
  card.append(imageBlock(item, false));
  const body = createElement("div", "card-body");
  body.append(createElement("h2", "card-title", item.title));
  body.append(createElement("p", "price", formatPrice(item.current_price)));
  const metrics = createElement("div", "metrics");
  const confidence = item.data_confidence;
  const price = item.price_analysis;
  metrics.append(metric("データ信頼度", `${confidence.score.toFixed(1)} / 100 · ${confidence.label.ja}`));
  const pricePosition = price.observed_set_percentile === null ? "データなし" : `観測セット内 約${Math.round(price.observed_set_percentile)}%`;
  const priceBand = price.price_band ? ` · ${price.price_band.ja}` : "";
  metrics.append(metric("価格位置", `${pricePosition}${priceBand}`));
  body.append(metrics);
  body.append(createElement("p", "observed-at", `最終観測 ${formatDate(item.last_observed_at)}`));
  const link = createElement("a", "detail-link", "詳細を見る");
  link.href = `item.html?id=${encodeURIComponent(item.public_id)}`;
  body.append(link);
  card.append(body);
  return card;
}

function populateSelect(select, values, labels) {
  values.forEach((value) => {
    const option = createElement("option", "", labels.get(value) || value);
    option.value = value;
    select.append(option);
  });
}

function applyIndexFilters() {
  const query = document.getElementById("search").value.trim().toLocaleLowerCase("ja-JP");
  const confidence = document.getElementById("confidence-filter").value;
  const band = document.getElementById("band-filter").value;
  const sort = document.getElementById("sort").value;
  state.filtered = state.items.filter((item) => {
    const queryMatch = !query || item.title.toLocaleLowerCase("ja-JP").includes(query);
    const confidenceMatch = !confidence || item.data_confidence.label.code === confidence;
    const itemBand = item.price_analysis.price_band ? item.price_analysis.price_band.code : "";
    return queryMatch && confidenceMatch && (!band || itemBand === band);
  });
  const numberOrInfinity = (value, descending) => Number.isFinite(value) ? value : (descending ? -Infinity : Infinity);
  state.filtered.sort((a, b) => {
    if (sort === "price-asc") return numberOrInfinity(a.current_price, false) - numberOrInfinity(b.current_price, false);
    if (sort === "price-desc") return numberOrInfinity(b.current_price, true) - numberOrInfinity(a.current_price, true);
    if (sort === "confidence-desc") return b.data_confidence.score - a.data_confidence.score;
    return new Date(b.last_observed_at).getTime() - new Date(a.last_observed_at).getTime();
  });
  state.page = 1;
  renderIndexPage();
}

function renderIndexPage() {
  const grid = document.getElementById("item-grid");
  clearNode(grid);
  const totalPages = Math.max(1, Math.ceil(state.filtered.length / PAGE_SIZE));
  state.page = Math.min(state.page, totalPages);
  const start = (state.page - 1) * PAGE_SIZE;
  state.filtered.slice(start, start + PAGE_SIZE).forEach((item) => grid.append(makeCard(item)));
  if (state.filtered.length === 0) grid.append(createElement("p", "muted", "条件に一致するデータがありません。"));
  document.getElementById("result-count").textContent = `${state.filtered.length}件を表示対象にしています`;
  document.getElementById("page-status").textContent = `${state.page} / ${totalPages}`;
  document.getElementById("prev-page").disabled = state.page <= 1;
  document.getElementById("next-page").disabled = state.page >= totalPages;
}

async function initializeIndex() {
  const [manifest, index] = await Promise.all([
    fetchJson("public-data/manifest.json"),
    fetchJson("public-data/index.json"),
  ]);
  validateManifest(manifest);
  if (!index || !Array.isArray(index.items) || index.items.length !== manifest.item_count) throw new Error("データ件数が一致しません");
  setPreviewStatus(manifest);
  state.items = index.items.slice();
  document.getElementById("item-count").textContent = `${manifest.item_count} items`;
  document.getElementById("as-of").textContent = formatDate(manifest.as_of);
  const confidenceLabels = new Map();
  const bandLabels = new Map();
  state.items.forEach((item) => {
    confidenceLabels.set(item.data_confidence.label.code, item.data_confidence.label.ja);
    if (item.price_analysis.price_band) bandLabels.set(item.price_analysis.price_band.code, item.price_analysis.price_band.ja);
  });
  populateSelect(document.getElementById("confidence-filter"), [...confidenceLabels.keys()].sort(), confidenceLabels);
  populateSelect(document.getElementById("band-filter"), [...bandLabels.keys()].sort(), bandLabels);
  ["search", "sort", "confidence-filter", "band-filter"].forEach((id) => {
    const control = document.getElementById(id);
    control.addEventListener(id === "search" ? "input" : "change", applyIndexFilters);
  });
  document.getElementById("prev-page").addEventListener("click", () => { state.page -= 1; renderIndexPage(); });
  document.getElementById("next-page").addEventListener("click", () => { state.page += 1; renderIndexPage(); });
  applyIndexFilters();
}

function definitionList(entries) {
  const list = createElement("dl", "stats-list");
  entries.forEach(([label, value]) => {
    list.append(createElement("dt", "", label));
    list.append(createElement("dd", "", value));
  });
  return list;
}

function confidencePanel(data) {
  const panel = createElement("section", "panel detail-panel");
  panel.append(createElement("h2", "", "データ信頼度の内訳"));
  panel.append(createElement("p", "", `総合：${data.score.toFixed(1)} / 100 · ${data.label.ja}`));
  panel.append(createElement("p", "muted", "この指標は作品の品質・人気・内容を評価するものではありません。"));
  const names = new Map([
    ["freshness", "鮮度"], ["observation_depth", "観測深度"], ["metadata_completeness", "基本情報"],
    ["price_data", "価格データ"], ["temporal_confidence", "時系列信頼度"],
  ]);
  Object.entries(data.components).forEach(([key, value]) => {
    const row = createElement("div", "component");
    const head = createElement("div", "component-head");
    head.append(createElement("span", "", names.get(key) || key));
    head.append(createElement("span", "", `${Number(value).toFixed(1)} / 100`));
    const bar = createElement("div", "bar");
    const fill = createElement("div", "bar-fill");
    fill.style.width = `${Math.max(0, Math.min(100, Number(value)))}%`;
    bar.append(fill);
    row.append(head, bar);
    panel.append(row);
  });
  return panel;
}

function comparisonBlock(title, entityLabel, comparisons, entities, minimum) {
  const panel = createElement("section", "panel detail-panel");
  panel.append(createElement("h2", "", title));
  const namesByPublicId = new Map(entities.map((entity) => [entity.public_id, entity.name]));
  const available = comparisons.filter((entry) => entry.status === "available" && entry.sample_size >= minimum);
  if (available.length === 0) {
    panel.append(createElement("p", "muted", "比較データ不足"));
    return panel;
  }
  available.forEach((entry, index) => {
    const row = createElement("div", "comparison");
    if (index >= 4) row.hidden = true;
    const entityName = namesByPublicId.get(entry.public_group_id);
    row.append(createElement("p", "", entityName ? `${entityLabel}：${entityName}` : `${entityLabel}名：表示データなし`));
    row.append(createElement("p", "muted", `標本数 ${entry.sample_size} · 観測セット内位置 約${Math.round(entry.percentile)}%`));
    row.append(createElement("p", "muted", `中央値 ${formatPrice(entry.median)}`));
    panel.append(row);
  });
  if (available.length > 4) {
    const toggle = createElement("button", "comparison-toggle", `すべて表示（${available.length}件）`);
    toggle.type = "button";
    toggle.addEventListener("click", () => {
      const expanding = toggle.dataset.expanded !== "true";
      panel.querySelectorAll(".comparison").forEach((row, index) => { row.hidden = !expanding && index >= 4; });
      toggle.dataset.expanded = expanding ? "true" : "false";
      toggle.textContent = expanding ? "表示を戻す" : `すべて表示（${available.length}件）`;
    });
    panel.append(toggle);
  }
  return panel;
}

function metadataPanel(metadata) {
  const panel = createElement("section", "panel detail-panel");
  panel.append(createElement("h2", "", "基本情報"));
  const labels = new Map([["maker", "メーカー"], ["series", "シリーズ"], ["actress", "出演者"], ["genre", "ジャンル"]]);
  Object.entries(metadata).forEach(([key, entities]) => {
    if (!Array.isArray(entities) || entities.length === 0) return;
    const group = createElement("div", "metadata-group");
    group.append(createElement("h3", "", labels.get(key) || key));
    const tags = createElement("div", "tag-list");
    entities.forEach((entity) => tags.append(createElement("span", "tag", entity.name)));
    group.append(tags);
    panel.append(group);
  });
  return panel;
}

function pricePanel(item) {
  const analysis = item.price_analysis;
  const history = analysis.price_history;
  const panel = createElement("section", "panel detail-panel");
  panel.append(createElement("h2", "", "価格分析"));
  panel.append(definitionList([
    ["現在価格", formatPrice(item.current_price)],
    ["観測セット内の価格位置", analysis.observed_set_percentile === null ? "データなし" : `約${Math.round(analysis.observed_set_percentile)}%`],
    ["価格位置帯", analysis.price_band ? analysis.price_band.ja : "データなし"],
    ["価格観測回数", `${history.price_observation_count}回`],
    ["異なる観測日", `${history.distinct_price_observation_dates}日`],
    ["価格観測期間", `${Number(history.price_observation_span_days).toFixed(2)}日`],
    ["最小観測価格", formatPrice(history.min_observed_price)],
    ["最大観測価格", formatPrice(history.max_observed_price)],
  ]));
  panel.append(createElement("p", "muted", "価格位置は現在のDATA LAB観測セット内のみの記述的な参考値です。市場価格やお得度を表しません。"));
  return panel;
}

function renderDetail(item) {
  const root = document.getElementById("detail-root");
  clearNode(root);
  const hero = createElement("section", "panel detail-hero");
  hero.append(imageBlock(item, true));
  const copy = createElement("div", "detail-copy");
  copy.append(createElement("p", "section-label", "OBSERVATION DETAIL"));
  copy.append(createElement("h2", "detail-title", item.title));
  copy.append(createElement("p", "price", formatPrice(item.current_price)));
  copy.append(createElement("p", "detail-lead", `最終観測 ${formatDate(item.last_observed_at)}`));
  if (item.item_url) {
    const link = createElement("a", "official-link", "公式ページを見る");
    link.href = item.item_url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    copy.append(link);
  }
  hero.append(copy);
  root.append(hero);
  const grid = createElement("div", "detail-grid");
  grid.append(confidencePanel(item.data_confidence));
  grid.append(pricePanel(item));
  grid.append(metadataPanel(item.metadata));
  grid.append(comparisonBlock("ジャンル内価格比較", "ジャンル", item.price_analysis.genre_comparisons, item.metadata.genre, 20));
  grid.append(comparisonBlock("メーカー内価格比較", "メーカー", item.price_analysis.maker_comparison.comparisons, item.metadata.maker, 10));
  root.append(grid);
}

async function initializeDetail() {
  const id = new URLSearchParams(window.location.search).get("id");
  if (!id || !/^itm_[0-9a-f]{24}$/.test(id)) throw new Error("公開IDが正しくありません");
  const manifest = await fetchJson("public-data/manifest.json");
  validateManifest(manifest);
  setPreviewStatus(manifest);
  const shard = id.slice(4, 6);
  const documentData = await fetchJson(`public-data/items/${shard}/${encodeURIComponent(id)}.json`);
  if (!documentData || documentData.public_schema_version !== EXPECTED_SCHEMA_VERSION || !documentData.item || documentData.item.public_id !== id) throw new Error("詳細データ形式が一致しません");
  renderDetail(documentData.item);
}

function showFatalError(error) {
  const box = document.getElementById("fatal-error");
  if (!box) return;
  box.hidden = false;
  box.textContent = error instanceof Error ? error.message : "表示できませんでした";
}

document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page;
  const initializer = page === "detail" ? initializeDetail : initializeIndex;
  initializer().catch(showFatalError);
});
