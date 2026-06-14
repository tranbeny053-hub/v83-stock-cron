const sessionStatus = document.querySelector("#sessionStatus");
const loginPanel = document.querySelector("#loginPanel");
const workspace = document.querySelector("#workspace");
const overviewTemplate = document.querySelector("#overviewTemplate");
const singleResult = document.querySelector("#singleResult");
const detailPanel = document.querySelector("#detailPanel");
const refreshButton = document.querySelector("#refreshButton");
const lastRefreshed = document.querySelector("#lastRefreshed");
const persistenceStatusBadge = document.querySelector("#persistenceStatusBadge");
const devModeStatus = document.querySelector("#devModeStatus");
const watchlistStorageKey = "ucpe_watchlist_symbols";
const heatLegend = "Signal heat — not risk";
const modelReadinessCopy = "Model readiness: Heuristic (uncalibrated) — accuracy not yet measured.";
const singleTimeframes = ["15m", "1H", "4H", "1D", "1W", "1M"];
const singlePayloads = new Map();
const watchlistPayloads = new Map();
const refreshCooldownMs = 15000;
let refreshReadyAt = 0;
let refreshTimer = null;
let analysisActive = false;
let lastBatchRequest = null;
let currentWatchlistSymbol = null;
const scoreHeatBands = [
  {
    min: 86,
    max: 100,
    level: "Extreme / Burning",
    mainColor: "#FF1A1A",
    className: "heat-extreme",
  },
  { min: 71, max: 85, level: "Very Hot", mainColor: "#F43F3F", className: "heat-very-hot" },
  { min: 56, max: 70, level: "Hot", mainColor: "#DC2626", className: "heat-hot" },
  { min: 41, max: 55, level: "Warm", mainColor: "#9F3A3A", className: "heat-warm" },
  { min: 21, max: 40, level: "Low", mainColor: "#5A4545", className: "heat-low" },
  { min: 0, max: 20, level: "Cold / Neutral", mainColor: "#374151", className: "heat-cold" },
];

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (response.ok) {
    updateStatusFromPayload(payload);
  }
  if (!response.ok) {
    throw new Error(payload?.detail?.error?.message || "Request failed");
  }
  return payload;
}

function updateStatusFromPayload(payload = {}) {
  const status =
    payload.persistence_status ||
    payload.debug?.persistence_status ||
    payload.detail_view?.debug_lite?.persistence_status ||
    payload.system?.persistence_status;
  if (status) {
    updatePersistenceStatus(status);
  }
  if (payload.system?.dev_mode) {
    updateDevModeUx(payload.system.dev_mode);
  }
}

function updatePersistenceStatus(status) {
  const safeStatus = status || "UNKNOWN";
  persistenceStatusBadge.textContent = `Persistence: ${safeStatus}`;
  persistenceStatusBadge.dataset.persistenceStatus = safeStatus;
  persistenceStatusBadge.classList.remove("status-ok", "status-warn", "status-unknown");
  if (safeStatus === "OK") {
    persistenceStatusBadge.classList.add("status-ok");
  } else if (safeStatus === "STATELESS" || safeStatus === "UNAVAILABLE") {
    persistenceStatusBadge.classList.add("status-warn");
  } else {
    persistenceStatusBadge.classList.add("status-unknown");
  }
}

function updateDevModeUx(devMode = {}) {
  const enabled = devMode.enabled === true;
  const configured = devMode.configured === true;
  const codeInput = document.querySelector("#devCode");
  const submitButton = document.querySelector("#devForm button[type='submit']");
  const loadRunsButton = document.querySelector("#loadRuns");
  if (!enabled) {
    devModeStatus.textContent = "Dev Mode is disabled in this deployment.";
    codeInput.disabled = true;
    submitButton.disabled = true;
    loadRunsButton.disabled = true;
    return;
  }
  if (!configured) {
    devModeStatus.textContent = "Dev Mode is enabled, but no Dev Mode code is configured.";
    codeInput.disabled = true;
    submitButton.disabled = true;
    loadRunsButton.disabled = true;
    return;
  }
  devModeStatus.textContent = "Dev Mode is available. Re-auth to load debug tools.";
  codeInput.disabled = false;
  submitButton.disabled = false;
  loadRunsButton.disabled = false;
}

async function loadSystemStatus() {
  try {
    await api("/v1/system_status");
  } catch {
    updatePersistenceStatus("UNKNOWN");
  }
}

function showPanel(name) {
  for (const button of document.querySelectorAll(".tab")) {
    button.classList.toggle("active", button.dataset.tab === name);
  }
  for (const panel of ["single", "batch", "watchlist", "dev"]) {
    document.querySelector(`#${panel}Panel`).classList.toggle("hidden", panel !== name);
  }
  hideDetail();
  if (name === "watchlist") {
    loadWatchlist();
  }
}

function setLoading(id, active) {
  document.querySelector(id).classList.toggle("hidden", !active);
}

function setAnalysisActive(active) {
  analysisActive = active;
  updateRefreshButton();
}

function updateRefreshButton() {
  const now = Date.now();
  const cooldownActive = now < refreshReadyAt;
  refreshButton.disabled = analysisActive || cooldownActive || workspace.classList.contains("hidden");
  if (analysisActive) {
    refreshButton.textContent = "Re-analyzing...";
  } else if (cooldownActive) {
    refreshButton.textContent = `Re-analyze (${Math.ceil((refreshReadyAt - now) / 1000)}s)`;
  } else {
    refreshButton.textContent = "Re-analyze";
  }
  if (refreshTimer) {
    clearTimeout(refreshTimer);
    refreshTimer = null;
  }
  if (cooldownActive) {
    refreshTimer = setTimeout(updateRefreshButton, 1000);
  }
}

function markRefreshed() {
  lastRefreshed.textContent = `last refreshed at ${new Date().toLocaleTimeString()}`;
  refreshReadyAt = Date.now() + refreshCooldownMs;
  updateRefreshButton();
}

function activeTabName() {
  return document.querySelector(".tab.active")?.dataset.tab || "single";
}

function dataBannerText(display = {}) {
  if (display.is_live_data) {
    return `LIVE DATA - ${display.data_source}`;
  }
  if (display.data_source === "FIXTURE_DEMO") {
    return `DEMO DATA - ${display.data_source}`;
  }
  if (display.data_source === "UNAVAILABLE") {
    return `DATA UNAVAILABLE - ${display.data_source}`;
  }
  return `DEGRADED DATA - ${display.data_source || "DEGRADED"}`;
}

function formatNumber(value, digits = 2) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "n/a";
  }
  return value.toFixed(digits);
}

function formatPct(value) {
  return `${formatNumber(value)}%`;
}

function formatValue(value) {
  if (value === null || value === undefined) {
    return "n/a";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : formatNumber(value, 4);
  }
  if (typeof value === "boolean") {
    return value ? "yes" : "no";
  }
  if (Array.isArray(value)) {
    return value.length ? value.join(", ") : "none";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function getScoreHeatBand(score) {
  const value = typeof score === "number" && Number.isFinite(score) ? score : 0;
  const safeScore = Math.max(0, Math.min(100, value));
  return (
    scoreHeatBands.find((band) => safeScore >= band.min && safeScore <= band.max) ||
    scoreHeatBands[scoreHeatBands.length - 1]
  );
}

function firstReason(payload) {
  const display = payload.frontend_display || {};
  const candidates = [
    ...(display.key_reasons || []),
    ...(display.data_quality_warnings || []),
    ...(display.execution_warnings || []),
    ...(display.news_warnings || []),
  ];
  return candidates.find(Boolean) || "OK";
}

function overviewCard(payload) {
  const node = overviewTemplate.content.firstElementChild.cloneNode(true);
  const display = payload.frontend_display;
  const timeframe = payload.timeframes?.primary || "n/a";
  const heatBand = getScoreHeatBand(display.total_score);
  node.classList.add("timeframe-card");
  node.classList.add(heatBand.className);
  node.dataset.timeframeCard = timeframe;
  node.style.setProperty("--heat-main", heatBand.mainColor);
  node.style.setProperty("--heat-border", heatBand.mainColor);
  node.querySelector("h2").textContent = `${payload.normalized_symbol} · ${
    display.horizon_approx_label || timeframe
  }`;
  const demoBanner = document.createElement("p");
  demoBanner.className = "demo-banner";
  demoBanner.textContent = dataBannerText(display);
  node.insertBefore(demoBanner, node.querySelector("dl"));
  const values = [
    ["Disposition", display.disposition],
    ["Score", display.total_score],
    ["Setup", display.timeframe_label || timeframe],
    ["Horizon", display.horizon_label || "multi-bar horizon"],
    ["Up", formatPct(display.prob_up_pct)],
    ["Down", formatPct(display.prob_down_pct)],
    ["Timeout", formatPct(display.prob_timeout_pct)],
    ["Model readiness", display.model_readiness_label || modelReadinessCopy],
    ["Data", display.is_live_data ? "LIVE" : display.data_source],
    ["Source", display.data_source],
    ["Gate", firstReason(payload)],
    ["Heat", heatBand.level],
  ];
  appendDefinitionRows(node.querySelector("dl"), values);
  const note = node.querySelector(".news-note");
  note.textContent =
    payload.analysis_mode === "METRICS_ONLY"
      ? "News disabled in METRICS_ONLY."
      : payload.news_addon_state.status;
  node.querySelector(".detail-button").addEventListener("click", () => openDetail(payload));
  node.addEventListener("click", (event) => {
    if (event.target.closest("button")) {
      return;
    }
    openDetail(payload);
  });
  return node;
}

function loadingCard(timeframe) {
  const node = document.createElement("article");
  node.className = "result-card timeframe-card loading-card";
  node.dataset.timeframeCard = timeframe;
  node.innerHTML = `
    <header><h2>${timeframe}</h2><span class="badge">Loading</span></header>
    <p class="muted">Awaiting backend analysis.</p>
    <p class="heat-mini">${heatLegend}</p>
  `;
  return node;
}

function errorCard(timeframe, error) {
  const node = document.createElement("article");
  node.className = "result-card timeframe-card error-card";
  node.dataset.timeframeCard = timeframe;
  const header = document.createElement("header");
  const heading = document.createElement("h2");
  const badge = document.createElement("span");
  const message = document.createElement("p");
  const heat = document.createElement("p");
  heading.textContent = timeframe;
  badge.className = "badge danger";
  badge.textContent = "Error";
  message.textContent = error.message || "Analysis failed.";
  heat.className = "heat-mini";
  heat.textContent = heatLegend;
  header.append(heading, badge);
  node.append(header, message, heat);
  return node;
}

function appendDefinitionRows(dl, values) {
  for (const [label, value] of values) {
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = label;
    dd.textContent = formatValue(value);
    dl.append(dt, dd);
  }
}

function renderResults(target, payloads, errors = []) {
  target.replaceChildren();
  for (const payload of payloads) {
    target.append(overviewCard(payload));
  }
  for (const item of errors) {
    const node = document.createElement("article");
    node.className = "result-card";
    node.textContent = `Item ${item.index + 1}: ${item.detail.error.code}`;
    target.append(node);
  }
}

function replaceTimeframeCard(target, timeframe, node) {
  const current = target.querySelector(`[data-timeframe-card="${timeframe}"]`);
  if (current) {
    current.replaceWith(node);
  } else {
    target.append(node);
  }
}

function renderTimeframePlaceholders(target) {
  target.replaceChildren(...singleTimeframes.map((timeframe) => loadingCard(timeframe)));
  hideDetail();
}

async function runTimeframeSet({ symbol, analysisMode, target, loadingSelector, payloadStore }) {
  payloadStore.clear();
  renderTimeframePlaceholders(target);
  setLoading(loadingSelector, true);
  setAnalysisActive(true);
  try {
    const requests = singleTimeframes.map(async (timeframe) => {
      try {
        const payload = await api("/v1/analyze", {
          method: "POST",
          body: JSON.stringify({
            symbol,
            analysis_mode: analysisMode,
            timeframe,
          }),
        });
        payloadStore.set(timeframe, payload);
        payloadStore.set(payload.run_id, payload);
        replaceTimeframeCard(target, timeframe, overviewCard(payload));
      } catch (error) {
        replaceTimeframeCard(target, timeframe, errorCard(timeframe, error));
      }
    });
    await Promise.allSettled(requests);
    markRefreshed();
  } finally {
    setAnalysisActive(false);
    setLoading(loadingSelector, false);
  }
}

async function runSingleAnalysis(form) {
  await runTimeframeSet({
    symbol: String(form.get("symbol") || "").trim(),
    analysisMode: form.get("analysis_mode"),
    target: singleResult,
    loadingSelector: "#singleLoading",
    payloadStore: singlePayloads,
  });
}

async function openDetail(payload) {
  let detailView = null;
  if (payload.run_id && payload.frontend_display?.detail_available !== false) {
    try {
      detailView = await api(`/v1/analyze/detail/${payload.run_id}`);
    } catch {
      detailView = null;
    }
  }
  if (!detailView && payload.detail_view && Object.keys(payload.detail_view).length > 0) {
    detailView = payload.detail_view;
  }
  if (!detailView) {
    renderDetailUnavailable(payload);
    return;
  }
  renderStructuredDetail(payload, detailView);
  detailPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function hideDetail() {
  detailPanel.replaceChildren();
  detailPanel.classList.add("hidden");
}

function renderDetailUnavailable(payload) {
  const message = document.createElement("p");
  message.className = "muted";
  message.textContent = "Detail Analysis is unavailable for this result.";
  detailPanel.replaceChildren(
    section("Detail Analysis", [
      keyValueTable([
        ["Symbol", payload?.normalized_symbol],
        ["Run ID", payload?.run_id],
        ["Status", "Unavailable"],
      ]),
      message,
    ]),
  );
  detailPanel.classList.remove("hidden");
  detailPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function section(title, children) {
  const node = document.createElement("section");
  node.className = "detail-section";
  const heading = document.createElement("h3");
  heading.textContent = title;
  node.append(heading, ...children);
  return node;
}

function keyValueTable(values) {
  const dl = document.createElement("dl");
  dl.className = "detail-kv";
  appendDefinitionRows(dl, values);
  return dl;
}

function objectTable(value) {
  const table = document.createElement("table");
  table.className = "detail-table";
  const body = document.createElement("tbody");
  for (const [key, item] of Object.entries(value || {})) {
    const row = document.createElement("tr");
    const label = document.createElement("th");
    const content = document.createElement("td");
    label.textContent = key.replaceAll("_", " ");
    if (item && typeof item === "object") {
      const nested = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = Array.isArray(item) ? `${item.length} items` : "View";
      const pre = document.createElement("pre");
      pre.textContent = JSON.stringify(item, null, 2);
      nested.append(summary, pre);
      content.append(nested);
    } else {
      content.textContent = formatValue(item);
    }
    row.append(label, content);
    body.append(row);
  }
  table.append(body);
  return table;
}

function listBlock(items = []) {
  const list = document.createElement("ul");
  list.className = "detail-list";
  for (const item of items || []) {
    const entry = document.createElement("li");
    entry.textContent = String(item);
    list.append(entry);
  }
  if (!list.children.length) {
    const entry = document.createElement("li");
    entry.textContent = "none";
    list.append(entry);
  }
  return list;
}

function jsonFilename(payload) {
  const symbol = String(payload.normalized_symbol || payload.symbol || "symbol")
    .replaceAll("/", "-")
    .replace(/[^\w.-]+/g, "-");
  const timeframe = payload.timeframes?.primary ? `${payload.timeframes.primary}_` : "";
  const runId = payload.run_id || "run";
  return `ucpe_${symbol}_${timeframe}${runId}.json`;
}

function downloadPayloadJson(payload) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = jsonFilename(payload);
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function downloadJsonButton(payload) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "download-json-button";
  button.textContent = "Download JSON";
  button.addEventListener("click", () => downloadPayloadJson(payload));
  return button;
}

function briefListGroup(title, items) {
  const group = document.createElement("div");
  group.className = "brief-list-group";
  const heading = document.createElement("h4");
  heading.textContent = title;
  group.append(heading, listBlock(items));
  return group;
}

function renderDecisionBrief(brief = {}) {
  return section("Decision Brief", [
    keyValueTable([
      ["Action", brief.action],
      ["Horizon", `${brief.timeframe_label || "setup"} / ${brief.horizon_label || "horizon"}`],
      ["Model readiness", modelReadinessCopy],
      ["Calibration", brief.calibration_status],
      ["Reliability", brief.reliability_status],
      ["Profitability claim", brief.profitability_claim ? "yes" : "false"],
      ["State summary", brief.state_summary],
      ["Volatility reference", brief.volatility_reference?.note],
      ["Risk note", brief.risk_note],
      ["Disclaimer", brief.disclaimer],
    ]),
    briefListGroup("Key Reasons", brief.key_reasons),
    briefListGroup("Hard Blockers", brief.hard_blockers),
    briefListGroup("Watchlist Triggers", brief.watchlist_triggers),
    briefListGroup("Invalidation Conditions", brief.invalidation_conditions),
  ]);
}

function renderStructuredDetail(payload, detailView) {
  const display = payload.frontend_display || {};
  const dataQuality = payload.data_quality || {};
  const providerState = payload.provider_state || {};
  const gate = payload.gate_result || {};
  const details = detailView || {};
  const decisionBrief = payload.decision_brief || details.decision_brief || {};
  const newsCopy =
    payload.analysis_mode === "METRICS_ONLY"
      ? "News analysis disabled for this run."
      : payload.news_addon_state?.status || "UNAVAILABLE";

  const rawJson = document.createElement("details");
  rawJson.className = "raw-json";
  const summary = document.createElement("summary");
  summary.textContent = "Debug / Raw JSON";
  const pre = document.createElement("pre");
  pre.textContent = JSON.stringify(payload, null, 2);
  rawJson.append(summary, pre);

  detailPanel.replaceChildren(
    section("Overview", [
      downloadJsonButton(payload),
      keyValueTable([
        ["Symbol", payload.normalized_symbol],
        ["Timeframe", payload.timeframes?.timeframe_label || payload.timeframes?.primary],
        ["Horizon", payload.timeframes?.horizon_label],
        ["Analysis mode", payload.analysis_mode],
        ["Disposition", display.disposition],
        ["Score", display.total_score],
        ["As of UTC", payload.as_of_utc],
        ["Run ID", payload.run_id],
        ["Data source", display.data_source],
        ["Live data", display.is_live_data],
        ["Persistence", payload.debug?.persistence_status || details.debug_lite?.persistence_status],
      ]),
    ]),
    renderDecisionBrief(decisionBrief),
    section("Probability", [
      keyValueTable([
        ["Type", decisionBrief.probability_type],
        ["Up", formatPct(display.prob_up_pct)],
        ["Down", formatPct(display.prob_down_pct)],
        ["Timeout", formatPct(display.prob_timeout_pct)],
        ["Model readiness", display.model_readiness_label || modelReadinessCopy],
        ["Explanation", display.probability_explanation],
      ]),
    ]),
    section("Risk / Gates", [
      keyValueTable([
        ["Gate action", gate.action],
        ["Hard blocks", gate.hard_blocks],
        ["Warnings", dataQuality.warnings],
      ]),
      objectTable(details.risk_detail),
    ]),
    section("Market Data Quality", [
      keyValueTable([
        ["Status", dataQuality.status],
        ["Latest age seconds", dataQuality.latest_candle_age_seconds],
        ["Warnings", dataQuality.warnings],
        ["Failures", dataQuality.provider_failures],
        ["Data source", dataQuality.data_source],
        ["Live data", dataQuality.is_live_data],
      ]),
    ]),
    section("Provider State", [
      keyValueTable([
        ["Active provider", providerState.active_provider],
        ["Status", providerState.status],
        ["Cross-provider state", providerState.cross_provider_state],
        ["Fallback to single provider", providerState.fallback_to_single_provider],
        ["Disagreement bps", providerState.disagreement_bps],
        ["Reason", providerState.cross_provider_reason],
      ]),
      objectTable(providerState.providers),
    ]),
    section("Market Data v2 / Provider Observability", [
      keyValueTable([
        ["Symbol availability", dataQuality.symbol_availability],
        ["Cross-provider state", dataQuality.cross_provider_state],
        ["Fallback to single provider", dataQuality.fallback_to_single_provider],
        ["Disagreement bps", dataQuality.disagreement_bps],
      ]),
      objectTable(details.market_data_v2_detail || dataQuality.derived_market_metrics),
    ]),
    section("Quant Signals", [
      objectTable(details.metrics_detail),
      objectTable(details.liquidity_execution_detail),
    ]),
    section("News Add-on", [
      keyValueTable([
        ["State", newsCopy],
        ["Mode", payload.analysis_mode],
        ["Warnings", display.news_warnings],
      ]),
      objectTable(details.news_detail),
    ]),
    section("News Authority / Macro & Micro Context", [
      keyValueTable([
        ["Influence mode", payload.news_addon_state?.influence_mode],
        ["Influence", "0.0 advisory display only"],
        ["Provider status", payload.news_addon_state?.provider_status],
      ]),
      objectTable(details.news_detail?.news_evidence || payload.news_evidence),
      objectTable(details.news_detail?.macro_context || payload.macro_context),
      objectTable(payload.micro_news_context),
    ]),
    section("Debug / Raw JSON", [rawJson]),
  );
  detailPanel.classList.remove("hidden");
}

document.querySelector("#loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const code = new FormData(event.currentTarget).get("code");
  await api("/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
  loginPanel.classList.add("hidden");
  workspace.classList.remove("hidden");
  sessionStatus.textContent = "Ready";
  updateRefreshButton();
  await loadSystemStatus();
});

for (const button of document.querySelectorAll(".tab")) {
  button.addEventListener("click", () => showPanel(button.dataset.tab));
}

document.querySelector("#singleForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  await runSingleAnalysis(new FormData(event.currentTarget));
});

function batchRequestFromForm(form) {
  const symbols = String(form.get("symbols"))
    .split(/\s+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 5);
  return {
    symbols,
    analysisMode: form.get("analysis_mode"),
    timeframe: form.get("timeframe"),
  };
}

async function runBatchAnalysis(batchRequest) {
  hideDetail();
  setLoading("#batchLoading", true);
  setAnalysisActive(true);
  try {
    lastBatchRequest = batchRequest;
    const requests = batchRequest.symbols.map((symbol) => ({
      symbol,
      analysis_mode: batchRequest.analysisMode,
      timeframe: batchRequest.timeframe,
    }));
    const payload = await api("/v1/analyze_batch", {
      method: "POST",
      body: JSON.stringify({ requests }),
    });
    renderResults(document.querySelector("#batchResult"), payload.results, payload.errors);
    updateStatusFromPayload(payload.results?.[0] || {});
    markRefreshed();
  } finally {
    setAnalysisActive(false);
    setLoading("#batchLoading", false);
  }
}

document.querySelector("#batchForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  await runBatchAnalysis(batchRequestFromForm(new FormData(event.currentTarget)));
});

function readLocalWatchlist() {
  try {
    const parsed = JSON.parse(localStorage.getItem(watchlistStorageKey) || "[]");
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function writeLocalWatchlist(symbols) {
  localStorage.setItem(watchlistStorageKey, JSON.stringify([...new Set(symbols)].slice(0, 20)));
}

function setWatchlistStatus(status) {
  const target = document.querySelector("#watchlistStatus");
  updatePersistenceStatus(status);
  const browserFallback = status !== "OK";
  target.textContent = browserFallback
    ? `Watchlist persistence: ${status}. Browser fallback is active.`
    : "Watchlist persistence: OK";
}

function renderWatchlist(symbols, status) {
  const target = document.querySelector("#watchlistList");
  setWatchlistStatus(status);
  target.replaceChildren();
  if (!symbols.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "No symbols yet.";
    target.append(empty);
    return;
  }
  for (const symbol of symbols) {
    const row = document.createElement("article");
    row.className = "watchlist-row";
    const symbolButton = document.createElement("button");
    symbolButton.type = "button";
    symbolButton.className = "watchlist-symbol";
    symbolButton.textContent = symbol;
    symbolButton.addEventListener("click", () => openWatchlistSymbol(symbol));
    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "watchlist-remove";
    removeButton.textContent = "Remove";
    removeButton.addEventListener("click", () => removeWatchlistSymbol(symbol));
    row.append(symbolButton, removeButton);
    target.append(row);
  }
}

async function loadWatchlist() {
  try {
    const payload = await api("/v1/watchlist");
    let symbols = payload.symbols || [];
    if (payload.persistence_status !== "OK") {
      const localSymbols = readLocalWatchlist();
      symbols = localSymbols.length ? localSymbols : symbols;
      writeLocalWatchlist(symbols);
    }
    renderWatchlist(symbols, payload.persistence_status || "UNAVAILABLE");
  } catch (error) {
    renderWatchlist(readLocalWatchlist(), "UNAVAILABLE");
    document.querySelector("#watchlistStatus").title = error.message || "Watchlist unavailable";
  }
}

async function addWatchlistSymbol(symbol) {
  const payload = await api("/v1/watchlist", {
    method: "POST",
    body: JSON.stringify({ symbol }),
  });
  let symbols = payload.symbols || [];
  if (payload.persistence_status !== "OK") {
    symbols = [...new Set([...readLocalWatchlist(), ...symbols])].slice(0, 20);
    writeLocalWatchlist(symbols);
  }
  renderWatchlist(symbols, payload.persistence_status || "UNAVAILABLE");
}

async function removeWatchlistSymbol(symbol) {
  const payload = await api(`/v1/watchlist/${encodeURIComponent(symbol)}`, {
    method: "DELETE",
  });
  let symbols = payload.symbols || [];
  if (payload.persistence_status !== "OK") {
    symbols = readLocalWatchlist().filter((item) => item !== symbol);
    writeLocalWatchlist(symbols);
  }
  renderWatchlist(symbols, payload.persistence_status || "UNAVAILABLE");
}

async function openWatchlistSymbol(symbol) {
  currentWatchlistSymbol = symbol;
  hideDetail();
  document.querySelector("#watchlistList").classList.add("hidden");
  document.querySelector("#watchlistView").classList.remove("hidden");
  document.querySelector("#watchlistSymbolTitle").textContent = `${symbol} Watchlist Symbol View`;
  await runTimeframeSet({
    symbol,
    analysisMode: document.querySelector("#watchlistMode").value,
    target: document.querySelector("#watchlistResult"),
    loadingSelector: "#watchlistLoading",
    payloadStore: watchlistPayloads,
  });
}

document.querySelector("#watchlistForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const symbol = String(new FormData(event.currentTarget).get("symbol") || "").trim();
  if (!symbol) {
    return;
  }
  await addWatchlistSymbol(symbol);
});

document.querySelector("#backToWatchlist").addEventListener("click", () => {
  hideDetail();
  document.querySelector("#watchlistView").classList.add("hidden");
  document.querySelector("#watchlistList").classList.remove("hidden");
});

async function refreshCurrentView() {
  if (analysisActive || Date.now() < refreshReadyAt) {
    updateRefreshButton();
    return;
  }
  const tab = activeTabName();
  if (tab === "single") {
    await runSingleAnalysis(new FormData(document.querySelector("#singleForm")));
    return;
  }
  if (tab === "watchlist") {
    if (!document.querySelector("#watchlistView").classList.contains("hidden") && currentWatchlistSymbol) {
      await openWatchlistSymbol(currentWatchlistSymbol);
    } else {
      await loadWatchlist();
      markRefreshed();
    }
    return;
  }
  if (tab === "batch") {
    const request = lastBatchRequest || batchRequestFromForm(new FormData(document.querySelector("#batchForm")));
    await runBatchAnalysis(request);
    return;
  }
  await loadSystemStatus();
  markRefreshed();
}

refreshButton.addEventListener("click", async () => {
  try {
    await refreshCurrentView();
  } catch (error) {
    sessionStatus.textContent = error.message || "Refresh failed";
  }
});

document.querySelector("#devForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const code = new FormData(event.currentTarget).get("code");
  try {
    await api("/v1/auth/dev", {
      method: "POST",
      body: JSON.stringify({ code }),
    });
    document.querySelector("#devResult").textContent = "Dev Mode ready.";
  } catch (error) {
    document.querySelector("#devResult").textContent =
      devModeStatus.textContent || error.message || "Dev Mode unavailable.";
  }
});

document.querySelector("#loadRuns").addEventListener("click", async () => {
  const runs = await api("/v1/debug/runs");
  const target = document.querySelector("#devResult");
  target.textContent = JSON.stringify(runs, null, 2);
  for (const run of runs.runs) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `Export ${run.run_id}`;
    button.addEventListener("click", async () => {
      const exported = await api(`/v1/debug/export/${run.run_id}`);
      target.textContent = JSON.stringify(exported, null, 2);
    });
    target.append(document.createElement("br"), button);
  }
});

renderTimeframePlaceholders(singleResult);
updatePersistenceStatus("UNKNOWN");
updateDevModeUx({ enabled: false, configured: false });
updateRefreshButton();
